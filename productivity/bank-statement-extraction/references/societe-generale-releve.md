# Société Générale "RELEVÉ DE COMPTE" — layout notes

## Document shape

Cover page (no table) then N pages each repeating a table header; the last page
carries the totals block and legal text. Page-A4 geometry in points:

| element | position |
|---|---|
| table header row | y ≈ 117, cells `Date` x≈40, `Valeur` x≈82, `Nature de l'opération` x≈211, `Débit` x≈431, `Crédit` x≈511 |
| operation date | x ≈ 31 (plus the value date in the same line) |
| description | x ≈ 124 |
| débit amounts | right edge x1 ≈ 477 |
| crédit amounts | right edge x1 ≈ 560 |
| footer block | y ≥ 773 (`suite >>>`, `RA...`, `Société Générale`, `S.A. au capital`, `Siège Social`) |
| rotated side margin | x0 ≥ 565 (`N° ADEME : ...`, `RA...`) — exclude |

Constants used by the script: `TABLE_TOP = 120`, `TABLE_BOTTOM = 770`,
`MONEY_X = 400` (a money line starts right of this), `CREDIT_X = 500`
(amount right edge beyond this ⇒ crédit), `RIGHT_MARGIN_X = 565`.

## Patterns

```python
DATE_PAIR  = r"^(\d{2}/\d{2}/\d{4}) +(\d{2}/\d{2}/\d{4})$"   # date + valeur
AMOUNT     = r"^\d{1,3}(?:\.\d{3})*,\d{2}$"                     # 1.099,78
FOOTER     = r"^(Société Générale|S\.A\. au capital|Siège Social|RA\d{6}|N° ADEME|suite >>|\d+, bd |du \d{2}/\d{2}/\d{4} au )"
STOP       = r"^(TOTAUX DES MOUVEMENTS|NOUVEAU SOLDE)"
SOLDE_LINE = r"^\*\*\* SOLDE"
ACCOUNT    = r"n°\s+\d{5}\s+\d{5}\s+(\d{11})\s+\d{2}"
PERIOD     = r"du\s+(\d{2}/\d{2}/\d{4})\s+au\s+(\d{2}/\d{2}/\d{4})"
NEW_BALANCE= r"NOUVEAU SOLDE AU\s+(\d{2}/\d{2}/\d{4})\s*\+?\s*([\d.]+,\d{2})"
```

## Column mapping to the bank-export CSV

Target header (semicolon separated, CP1252, CRLF, no quoting):

```
Date de l'opération;Libellé;Détail de l'écriture;Montant de l'opération;Devise
```

| target column | source |
|---|---|
| `Date de l'opération` | the operation date (first of the date pair); the value date is dropped |
| `Détail de l'écriture` | all description lines of the block joined with one space |
| `Libellé` | first VISUAL line of the block, truncated to 18 chars (trailing space kept) |
| `Montant de l'opération` | débit → negative, crédit → positive; comma decimal, thousands dots stripped, no `+` |
| `Devise` | `EUR` |

Preamble (line 1, then a blank line, then the header):

```
<compte 11 digits>;<debut periode>;<fin periode>;<nb operations>;<date derniere op>;<solde> EUR
```

`<date derniere op>` is the LATEST operation date (i.e. the first data row of a
most-recent-first export). The balance is copied from `NOUVEAU SOLDE` in dot
decimal form (`2552.33 EUR`), unlike the amount column.

Rows are ordered most-recent-first in the reference export; the PDF itself is
chronological. Default the script to the reference order and keep `--keep-order`.

## Run / validate

```bash
cd /home/cricri/projects/pdf-releve-to-csv
./releve2csv "/path/to/releve.pdf" -o releve.csv --validate
```

`--validate` prints the parsed débit/crédit sums next to the `TOTAUX DES
MOUVEMENTS` figures and reports `OK`/`MISMATCH`. Treat a MISMATCH as a hard
stop — do not hand over the CSV. On the reference statement: 104 operations,
20 766,98 débit / 21 880,25 crédit, balance 2 552,33, all matching the PDF.
