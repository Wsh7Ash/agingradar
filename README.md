# agingradar

**Turn an invoices CSV into an aging report, a ranked chase list and a one-page HTML dunning view — the report a bookkeeper actually acts on.**

Aging is where small-business cash flow quietly dies: invoices pile up past
their due date, nobody remembers which customer always pays late, and the "who
should I call today" question gets answered by whoever shouts loudest.
`agingradar` answers it with numbers: aging buckets, an explainable chase
priority score, and a report your non-developer bookkeeper can read without
installing anything.

## Key features

- **Aging buckets** — current · 1–30 · 31–60 · 61–90 · 90+ days overdue,
  with per-bucket invoice counts and balances.
- **Explainable chase score (0–100)** — `amount × bucket × behaviour`:
  bigger debts count more, older buckets weigh more, and a customer who has
  paid late before gets a 15% nudge. Every component is visible in the report,
  so the number can be argued with.
- **Customer exposure table** — outstanding, overdue, oldest overdue days, and
  late-payment history per customer (with a ⚠ marker).
- **Three outputs** — markdown (PR/wiki/notes), a chase CSV (import into your
  accounting tool or mail merge), and a standalone HTML page (no external
  assets, open it from disk or attach it to an email).
- **Money done right** — integer cents (or the currency's minor unit: JPY,
  BHD, …), US *and* European number formats, `(50.00)`-style negatives.
- **Honest inputs** — CSVs with missing columns, wrong field counts, bad dates
  or unparseable amounts fail with `file:line: reason`, never silently.
- **CI-able** — `--fail-overdue-ratio 0.5` turns "half the book is overdue"
  into an exit code; `--as-of` makes reports reproducible.
- **Zero dependencies**, Python 3.10+ standard library only.

## Example

```shell
$ agingradar report examples/invoices-sample.csv --as-of 2026-10-18
# Aging report — 2026-10-18

- invoices analyzed: **12 open** (+ 2 paid, 2 ignored)
- outstanding: **$7,631.75**
- overdue: **$7,291.75** (96% of outstanding)
- average days to payment (paid invoices): **27.0**

## Aging buckets

| Bucket | Invoices | Balance |
|---|---|---|
| current | 1 | $340.00 |
| 1-30 | 1 | $199.00 |
| 31-60 | 3 | $607.50 |
| 61-90 | 2 | $1,325.25 |
| 90+ | 5 | $5,160.00 |

## Top customers by exposure

| Customer | Outstanding | Overdue | Oldest overdue | Late payments |
|---|---|---|---|---|
| Cedar Design Studio | $3,450.00 | $3,450.00 | 201d | 0 |
| Acme Bakery | $2,290.00 | $1,950.00 | 140d | 1 ⚠ |
| ...

## Chase list (top 5)

| # | Invoice | Customer | Due | Days | Bucket | Balance | Score |
|---|---|---|---|---|---|---|---|
| 1 | INV-1005 | Cedar Design Studio | 2026-03-31 | +201 | 90+ | $2,400.00 | 100 |
| 2 | INV-1001 | Acme Bakery | 2026-07-31 | +79 | 61-90 | $1,250.00 | 69 |
| ...
```

```shell
$ agingradar check examples/invoices-sample.csv
examples/invoices-sample.csv: OK — 16 invoices, 5 customer(s), currency USD, as of 2026-10-18
```

```shell
$ agingradar report examples/invoices-sample.csv --format html -o aging.html
wrote aging.html          # open in any browser, no server needed
```

Full offline demo (writes `results/`): `python examples/demo.py`.

## Architecture summary

```
invoices.csv ─► model.py ─► Ledger(invoices)          money as integer cents
                              │
                              ▼
                        aging.py ─► AgingReport        buckets, scores, aggregates
                              │
                              ▼
                        report.py ─► markdown / CSV / HTML
                              │
                        cli.py ─► exit codes (0 ok, 1 gate, 2 usage)
```

Details: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Requirements

- Python **3.10+** — standard library only, no network access.

## Installation

```shell
git clone https://github.com/Wsh7Ash/agingradar
cd agingradar
python -m pip install -e .
agingradar --version
```

Without installing: `PYTHONPATH=src python -m agingradar.cli report FILE.csv`.

## Quick start

```shell
agingradar check invoices.csv                       # is my file usable?
agingradar report invoices.csv                      # markdown aging report
agingradar report invoices.csv --format html -o aging.html
agingradar report invoices.csv --top 20 --format csv -o chase.csv
agingradar report invoices.csv --as-of 2026-09-30   # reproducible back-dated run
```

## Input format

```csv
number,customer,issue_date,due_date,amount,paid_amount,paid_date,status,currency
INV-1001,Acme Bakery,2026-07-01,2026-07-31,1250.00,,,open,USD
INV-1002,Acme Bakery,2026-05-01,2026-05-31,480.00,480.00,2026-06-20,paid,USD
```

Required columns: `number`, `customer`, `issue_date`, `due_date`, `amount`.
Optional: `paid_amount`, `paid_date`, `status`, `currency`.

- Statuses: `open/unpaid/sent/overdue/due` are open; `paid/settled/closed` are
  paid; `void/cancelled/draft/credit_note` are ignored entirely.
- Amounts accept `$1,234.56`, `1234,56`, `1.234,56`, `(50.00)`.
- Dates accept `YYYY-MM-DD`, `DD/MM/YYYY`, `MM/DD/YYYY`, `YYYY/MM/DD`, `DD.MM.YYYY`.

## Configuration

| Flag | Default | Meaning |
|---|---|---|
| `--as-of` | today | report date (`YYYY-MM-DD`) |
| `--format` | markdown | `markdown` / `html` / `csv` |
| `-o FILE` | stdout | write to file |
| `--top` | 10 | chase-list length |
| `--fail-overdue-ratio` | off | exit 1 when overdue share exceeds this (e.g. `0.5`) |

## Testing

```shell
python -m unittest discover -s tests -t . -v
```

55 tests cover money/date parsing (both number formats, negatives, minor
units), CSV loading errors with line numbers, bucket boundaries, scoring
(the small old debt outranks the big recent one), aggregates, all three
renderers, and every CLI path including the overdue-ratio gate.

## Project structure

```
agingradar/
├─ src/agingradar/
│  ├─ model.py      # Invoice, integer-cent money, CSV loading with line-accurate errors
│  ├─ aging.py      # buckets, chase scoring, report aggregates
│  ├─ report.py     # markdown / CSV / standalone HTML renderers
│  └─ cli.py        # report + check subcommands, exit codes
├─ tests/           # 55 unittest cases
├─ examples/
│  ├─ invoices-sample.csv   # 16-invoice fixture (late payers, partials, voids)
│  └─ demo.py               # deterministic demo → results/
├─ results/         # demo evidence (md, html, csv, json)
├─ docs/            # ARCHITECTURE.md, USAGE.md
└─ .github/workflows/ci.yml
```

## Limitations

- One aging run covers one CSV: no database, no live sync with Stripe/QBO.
- Chase scoring is a heuristic with published weights, not a credit model —
  read the components, adjust the weights in `aging.py`, or ignore the score
  and sort by balance (the report shows both).
- Partial payments reduce the balance but do not track *which* line items they
  settle; payment terms are assumed net-from-due-date.
- Multi-currency files are summed per currency in the totals; there is no FX
  conversion.
- "Average days to payment" only covers invoices with a `paid_date`.

## Roadmap

- Payment-plan / promise-to-pay column with its own tracking.
- Aging-by-contact-date ("last chased on …") to prioritize follow-ups.
- XLSX export and an ICS reminder generator for the chase list.
- Configurable weights via a `--weights` flag or config file.

## Security notes

agingradar reads only the CSV you name, performs no network requests, and
writes only to the output file you specify. Customer names and amounts stay
on your machine. See [docs/USAGE.md](docs/USAGE.md).

## Disclaimer

This is accounting software output, not financial, legal or credit advice.

## License

[MIT](LICENSE)