#!/usr/bin/env bash
# Carve deleted SQLite databases off a raw block device (read-only on the device).
#
#   sudo carve-sqlite-from-device.sh /dev/nvme0n1p4 ~/carve "marker one" "marker-two"
#
# Markers are strings that exist only in the lost data (row text, a URL, an id).
# One grep pass collects every 'SQLite format 3' header offset plus every marker
# offset (-b gives byte offsets, extra patterns cost no extra read). Each header is
# then carved at the exact length it declares, and EVERY candidate is opened with
# sqlite3 and reported with its table list — validation is by schema, never by the
# presence of a marker string (session stores, caches and logs on the same disk
# contain those strings too).
#
# Outputs in <outdir>: headers.txt markers.txt carved-<offset>.db report.txt
# A carved file that comes out malformed is still worth `sqlite3 carved.db ".recover"`.
set -uo pipefail

DEV=${1:?usage: $0 <block-device> <outdir> [marker ...]}
OUT=${2:?usage: $0 <block-device> <outdir> [marker ...]}
shift 2
mkdir -p "$OUT"

PAT='SQLite format 3'
for m in "$@"; do PAT="$PAT|$m"; done

echo "scanning $DEV read-only: this is the slow part (~500 MB/s) ..."
grep -a -b -o -E 'SQLite format 3' "$DEV" | cut -d: -f1 > "$OUT/headers.txt"
if [ "$#" -gt 0 ]; then grep -a -b -o -E "$PAT" "$DEV" | grep -v 'SQLite format 3' > "$OUT/markers.txt"; else : > "$OUT/markers.txt"; fi
unset PAT
echo "headers: $(wc -l < "$OUT/headers.txt")   marker hits: $(wc -l < "$OUT/markers.txt")"

python3 - "$DEV" "$OUT" "$@" <<'PY'
import os, sqlite3, struct, sys

dev, out, *markers = sys.argv[1:]
fd = os.open(dev, os.O_RDONLY)
read = lambda off, n: os.pread(fd, n, off)
marker_bytes = [m.encode() for m in markers]

marker_hits = []
for line in open(f"{out}/markers.txt"):
    off, _, token = line.rstrip("\n").partition(":")
    if token in markers:
        marker_hits.append(int(off))

headers = [int(l) for l in open(f"{out}/headers.txt") if l.strip()]
report = []
for h in headers:
    hdr = read(h, 100)
    if not hdr.startswith(b"SQLite format 3\x00"):
        continue
    page_size = struct.unpack(">H", hdr[16:18])[0]
    if page_size == 1:
        page_size = 65536
    page_count = struct.unpack(">I", hdr[28:32])[0]
    size = page_size * page_count if 0 < page_count < 1_000_000 else 32 * 1024 * 1024
    body = read(h, size)
    path = f"{out}/carved-{h}.db"
    with open(path, "wb") as fh:
        fh.write(body)
    has_marker = any(m in body for m in marker_bytes)
    try:
        con = sqlite3.connect(f"file:{path}?immutable=1", uri=True)
        tabs = [r[0] for r in con.execute("select name from sqlite_master where type='table'")]
        counts = []
        for t in tabs[:6]:
            try:
                counts.append(f"{t}={con.execute(f'select count(*) from \"{t}\"').fetchone()[0]}")
            except Exception:
                counts.append(f"{t}=?")
        con.close()
        note = f"tables({len(tabs)}): " + ", ".join(counts) if tabs else "no tables"
    except Exception as e:
        note = f"INVALID/MALFORMED ({str(e)[:60]}) - try .recover"
    line = f"{os.path.basename(path):32s} {size:>10d}B marker={str(has_marker):5s} {note}"
    report.append(line)
    print(line)

with open(f"{out}/report.txt", "w") as fh:
    fh.write("\n".join(report) + "\n")

print("\nmarker hits with no header within 1 MiB (raw fragments, no file header left):")
ordered = sorted(headers)
for m in marker_hits:
    prev = [x for x in ordered if x <= m]
    if not prev or m - prev[-1] > 1024 * 1024:
        print(f"  {m}")
PY
echo "done; triage report.txt, then see references/db-carve-restore.md"
