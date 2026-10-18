# Usage

Exit codes: `0` ok, `1` overdue-ratio gate tripped, `2` usage/input error.

## check — validate before you trust

```shell
agingradar check invoices.csv
agingradar check invoices.csv     # => invoices.csv: OK — 16 invoices, 5 customer(s), currency USD, as of 2026-10-18
```

`check` parses the whole file (so every bad row is reported with its line
number) without rendering anything.

## report

```shell
agingradar report invoices.csv                          # markdown to stdout
agingradar report invoices.csv --as-of 2026-09-30       # back-dated, reproducible
agingradar report invoices.csv --top 25                 # longer chase list
agingradar report invoices.csv --format csv -o chase.csv
agingradar report invoices.csv --format html -o aging.html
agingradar report invoices.csv --fail-overdue-ratio 0.5 # CI / cron gate
```

| Flag | Default | Meaning |
|---|---|---|
| `--as-of DATE` | today | aging date (`YYYY-MM-DD`) |
| `--format` | `markdown` | `markdown` \| `html` \| `csv` |
| `-o, --output` | stdout | output path |
| `--top N` | 10 | chase-list rows |
| `--fail-overdue-ratio R` | off | exit 1 when overdue/total > R (e.g. `0.4`) |

## CSV format

```csv
number,customer,issue_date,due_date,amount,paid_amount,paid_date,status,currency
INV-1001,Acme Bakery,2026-07-01,2026-07-31,1250.00,,,open,USD
INV-1002,Acme Bakery,2026-05-01,2026-05-31,480.00,480.00,2026-06-20,paid,USD
INV-1003,Blue Harbor,2026-08-10,2026-09-09,312.50,,,open,USD
```

Required: `number`, `customer`, `issue_date`, `due_date`, `amount`
(header names are case-insensitive; spaces become underscores).

Optional: `paid_amount`, `paid_date`, `status`, `currency`.

Exporting from common tools:

- **QuickBooks** → Reports › A/R Aging Detail › Export → add a `status` column.
- **Stripe** → Invoices list CSV; map `amount_due` → `amount`, `status`.
- **Spreadsheet** → "Save as CSV", comma-separated, ISO dates preferred.

## Typical workflows

**Monday morning collections**

```shell
agingradar report invoices.csv --top 10 --format html -o chase.html
# open chase.html, call the top 3, send the rest a reminder
```

**Month-end board note**

```shell
agingradar report invoices.csv --as-of $(date -d "last month" +%Y-%m-%d) -o aging-$(date +%Y-%m).md
```

**Cron alert when the book goes sideways**

```shell
0 8 * * 1  cd /books && agingradar report invoices.csv --fail-overdue-ratio 0.4 -o /tmp/aging.md || mail -s "Aging alert" boss@example.com < /tmp/aging.md
```

**Mail merge / import**

```shell
agingradar report invoices.csv --format csv -o chase.csv
# import chase.csv into your CRM or mail-merge tool
```

## Reading the score

`score_pct` is relative within one run (100 = the most urgent invoice). It
combines:

- **amount** — sqrt-scaled share of the largest open balance,
- **bucket** — 1.0 current → 3.0 for 90+ days,
- **behaviour** — ×1.15 when the customer has paid late before.

A small, very old debt can outrank a large, recently due one — that is
intentional, and the components are in the CSV export if you want to re-sort.

## Notes

- Money is handled as integer cents; JPY/KRW (0 decimals) and BHD/KWD
  (3 decimals) are supported.
- Multi-currency files are reported per currency; totals are not FX-converted.
- agingradar performs no network requests and keeps customer data local.