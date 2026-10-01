---
name: bank-statement-extraction
description: "Use when turning a bank statement PDF into CSV rows."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [PDF, Bank, CSV, Extraction, Finance]
    related_skills: [ocr-and-documents]
---

# Bank statement (relevé) → structured rows

## When to Use

Load this when the user asks to extract data from a bank statement PDF
(«relevé de compte» or any bank/statement export) into a CSV, spreadsheet or
structured rows — including "with the same columns as this file", where a
reference export defines the target schema. Also load it when an existing
statement extractor must be adapted to a new bank, a new period, or a changed
target format.

Turning a statement PDF into rows in an existing CSV schema. Two halves that
must be done in order: (1) reverse-engineer the exact target schema from the
reference file, (2) parse the PDF from LAYOUT, not from plain text, and prove
the parse against totals the statement prints itself.

## 1. Locate the inputs before writing code

The path the user names is often not where the file is. `~/Downloads` is
frequently empty; documents uploaded through Open WebUI are staged at
`~/openwebui_data/uploads/<uuid>_<original name>` with a UUID prefix prepended.
When a named attachment is missing, search the tree first
(`find /home/cricri -iname '*releve*' -o -iname '000*.csv'`, ignoring
`~/.cache`, `node_modules`, container storage) and check the uploads dir before
asking the user.

Confirm it is the right document, and say so out loud if it is not: read the
account number and period off page 1, compare with the name/figures the user
gave, and state the difference (a `releve (302).pdf` standing in for the
`releve (308).pdf` they meant). Never silently parse the wrong file.

## 2. Read the reference file before designing the parser

Decode and measure the target file before hypothesising about columns:

- Encoding: try `utf-8`, `utf-8-sig`, `cp1252`, `latin-1` in that order and keep
the first that decodes. French bank exports are usually CP1252, not UTF-8.
- Separator and line endings: inspect the raw bytes (`;`, `,`, `\t`; CRLF vs LF).
- Field-count histogram per row (`Counter(len(line.split(sep)))`). Varying counts
mean a field contains the separator, and naive splitting will silently shred
rows.
- The first lines may not be data: an info/metadata line, a blank line, then the
header row. Reproduce that preamble too, it is part of "same columns".

Derive each column's rule from ~20 sample rows, then VERIFY the rule against
100% of the reference rows. When a rule fails on a handful of rows, the rule is
subtly different — find the mechanism, do not special-case the outliers. Worked
example: SG's `Libellé` looked like `Détail[:18]`, but 5/500 rows disagreed;
the real rule is the first VISUAL line of the description block truncated to 18
chars (which is why `Libellé` keeps a trailing space mid-word, and why a
multi-line entry stops at the source line break instead of running on).

## 3. Parse the PDF from coordinates, not from flat text

Use pymupdf and work on visual lines with geometry:

```python
for block in page.get_text("dict")["blocks"]:
    for line in block.get("lines", []):
        text = "".join(s["text"] for s in line["spans"]).rstrip()
        x0, y0, x1, _ = line["bbox"]
```

Sort by `(round(y0, 1), x0)`. Rules that cost time when missed:

- The table header and its cells come back as SEPARATE text lines sharing one
y value (`Date`, `Valeur`, `Débit`, `Crédit` are four lines at the same y).
Never match a single header line; detect the header y by grouping lines with a
rounded y and looking for the column words in that group.
- Recover information the text layer does not carry, from geometry. When a bank
prints separate money columns with no sign, the amount's right edge x tells you
the column: debits right-align at one x, credits at another (test on `x1`, not
`x0`; use a threshold midway between the two).
- Exclude rotated side-margin text (`N° ADEME ...`, `RA...`) with an `x0`
threshold (~565 on A4 SG). Otherwise it leaks into every description it
overlaps.
- Detect the table bottom from the first footer-looking line below the header
(`Société Générale`, `Siège Social`, `suite >>>`, page-number block) instead of
a fixed y, and require the footer candidate to be inside the page body — a
right-margin line can otherwise truncate the table early.
- Stop at the summary rows (`TOTAUX DES MOUVEMENTS`, `NOUVEAU SOLDE`) and skip
intercalary balance lines (`*** SOLDE AU dd/mm/yyyy +/- n ***`).
- Operations are a state machine, not fixed-height blocks: a date-pair line
(`dd/mm/yyyy dd/mm/yyyy`, anchored to the whole line so interior dates like
`DATE: 01/07/2025 09:21` do not match) opens an operation, later description
lines append, and the money line sets the amount — the amount can arrive
BEFORE the last description line, so never close the block on the amount.
- Description lines join with a single space, preserving the PDF's internal
multiple spaces; keep the first visual line separately for the label column.

## 4. Validate against the statement's own printed totals

The statement prints its own arithmetic: a `TOTAUX DES MOUVEMENTS` row with the
débit and crédit sums, plus a closing balance. Sum your parsed rows and compare.
Require an exact match before delivering — this is what catches a flipped sign,
and it catches it even when the text layer looks right. A credit-side count and
subtotal matching exactly is a stronger check than the net sum, which can hide a
cancelling sign error. Also assert: no missing amounts, no empty details, every
data row has the expected field count.

## 5. Give the extractor its own interpreter

System `python3` on this box is PEP-668 managed, so `pip install --user pymupdf`
is refused. Build a dedicated venv next to the script and add a launcher so the
tool runs without activating anything:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --quiet --upgrade pip pymupdf
```

```bash
#!/usr/bin/env bash
exec "$(dirname "$(readlink -f "$0")")/.venv/bin/python" \
     "$(dirname "$(readlink -f "$0")")/pdf_releve_to_csv.py" "$@"
```

Never leave the user a script they cannot run because the interpreter is wrong.

## 6. Match the output byte-for-byte

Same encoding, separator, line endings (CRLF), preamble, header wording and
number formats as the reference. Number formats differ per column in the same
file: SG's `Montant` column is French comma decimal with NO thousands separator
(`-1557,86`, no `+` on credits) while the preamble's balance uses a dot decimal
(`798.95 EUR`). Verify by decoding your output and the reference side by side
(byte count, CRLF count, first three lines).

State every judgment call you made in the reply and give a flag to flip it —
notably row ORDER: reference exports may list most-recent-first while the
statement is chronological. Default to the reference's order, expose
`--keep-order`, and say which you chose.

## Reference implementation

`/home/cricri/projects/pdf-releve-to-csv/pdf_releve_to_csv.py` with launcher
`releve2csv` in the same directory (own `.venv`, pymupdf). SG-specific geometry,
patterns and the column-mapping table: `references/societe-generale-releve.md`.
Reuse it rather than rewriting; re-derive only when the bank or the target
schema changes.
