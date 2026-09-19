# Submission Pipeline Investigation — June 2026

## Problem

User reported: only 1 out of 10 Numerai Crypto submissions was labeled "On-Time"; all others were "Late" despite being inside round windows. Cron only submitted m5_draft, not m5_rc.

## Findings

### 1. Cron script only ran one model
The cron script `~/.hermes/scripts/numerai-crypto-submit.sh` called only `scripts/submit_live.py` (m5_draft). m5_rc was never submitted by cron. Fixed: script now runs both sequentially.

### 2. Sentiment fetch cron had wrong project path
`~/.hermes/scripts/fetch-sentiment.sh` referenced `/home/cricri/projects/numerai/numerai-crypto-bot` — doesn't exist. Should be `/home/cricri/projects/numerai-folders/numerai-crypto-bot`. This caused `status: error` every run.

### 3. "Late" receipts caused by 0 NMR staked
After investigating all 10 receipts against round windows, every submission landed inside its round's open→close window. The "Late" label is Numerai's way of saying "no NMR at risk, cannot stake" — not "missed the deadline."

Evidence:
- `api.get_account()['availableNmr']` = `0.00` for this account
- Numerai docs: "Late submissions do not impact the Meta Model, the at-risk NMR of a late submission is 0"
- The single On-Time receipt (Jun 7, Saturday, round 1284) could not be explained by any consistent timing rule (tested: 24h-from-open, same-calendar-day, first-submission-wins — all failed for other rounds)

Round windows from GraphQL `rounds(tournament:12)`:
| Round | Open (UTC) | Close (UTC) | Notes |
|-------|-----------|------------|-------|
| 1282 | Jun 4 12:00 | Jun 5 12:00 | Wed-Thu |
| 1283 | Jun 5 12:00 | Jun 6 12:00 | Thu-Fri |
| 1284 | Jun 6 12:00 | Jun 9 12:00 | Fri-Mon (weekend) |
| 1285 | Jun 9 12:00 | Jun 10 12:00 | Mon-Tue |

Cron runs at 09:30 UTC — 2.5h before nominal close. All submissions land inside windows.

### 4. numerapi download_file caches by file size
`numerapi.utils.download_file()` compares local file size against remote `content-length`. If they match, it skips re-download and logs "target file already exists" / "download complete". For `live.parquet` which often has the same byte size but different content across days, this causes stale data.

The cache lives at `crypto/v2.0/live.parquet` relative to project root. The `download_dataset()` wrapper in `src/numerai/auth.py` was relying on numerapi's default `dest_path` (the filename itself), so the cache persisted indefinitely.

Fix applied in `src/numerai/auth.py`: use `tempfile.NamedTemporaryFile` as `dest_path` → forces fresh download every call → copy to managed `data/raw/` location.

### 4a. Live download fails with a doubled `.parquet` extension (CRITICAL, silent)
`download_dataset()` in `src/numerai/auth.py` builds the local filename by replacing `/`→`_` and appending `.parquet`. The remote path passed to it already ends in `.parquet` (`crypto/v2.0/live.parquet`), so the file lands as `crypto_v2.0_live.parquet.parquet`. The caller then looks for `crypto_v2.0_live.parquet`, which never exists → the download step raises `ValueError: [Errno 2] No such file or directory: '...live.parquet.parquet' -> '...live.parquet'`.

Why it was silent: `numerapi`'s `download_file` caches by file size, so the first successful run (with a correctly-named cached file) masked the bug. Once the cache is cleared, every live download fails — and the training download (`crypto/v2.0/train.parquet`) fails identically, not just live.

Fix: strip any existing `.parquet` from the cleaned name before appending it in `download_dataset()`. **Always run a submission in `--test` mode (no upload) after any download-related code change** — the failure is a download-step error, not an upload error, so a live run would silently skip.

### 5. Cron schedule is correct
`30 11 * * 0-5` (CEST) = 09:30 UTC. Rounds close ~12:00 UTC. Buffer = 2.5h. The schedule covers Sun-Fri (CEST), which maps to the active trading week when rounds open.
