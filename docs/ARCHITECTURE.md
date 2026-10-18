# Architecture

## Goals

1. **Trustworthy numbers.** Money is integer cents (or the currency's minor
   unit); every input error names a file and a line.
2. **Explainable prioritization.** The chase score is three visible factors —
   nothing hidden, nothing magical.
3. **Usable by a non-developer.** The primary outputs are documents a
   bookkeeper can read and forward: markdown, CSV, and a self-contained HTML
   page.
4. **Deterministic.** Same CSV + same `--as-of` ⇒ byte-identical report.

## Components

### model.py — CSV → `Ledger`

- `parse_money` handles `$1,234.56`, `1234,56`, `1.234,56` and accounting
  negatives `(50.00)`, scaling by the currency's minor unit (JPY/KRW 0,
  USD/EUR/GBP 2, BHD/KWD 3). Everything downstream is `int` cents.
- `parse_date` tries six formats, all day/month unambiguous or ISO.
- `load_csv` normalizes headers (`Invoice Number` → `invoice_number`),
  validates the required columns up front, then reports each bad row as
  `file:line: reason` — including rows with too many fields (a classic
  spreadsheet export bug) — instead of mis-assigning values.
- Statuses map to three dispositions: open (aged), paid (history), ignored
  (void/draft/credit notes).
- UTF-8 BOM tolerant (`utf-8-sig`), blank lines skipped.

### aging.py — `Ledger` → `AgingReport`

- `bucket_for(days)`: `current` (due in the future or due today), `1-30`,
  `31-60`, `61-90`, `90+`.
- `_late_payer_map`: per customer, count of historical invoices paid ≥ 1 day
  after due. Drives both the ⚠ marker and the behaviour weight.
- Scoring per open invoice:

  ```
  score  = amount_weight × bucket_weight × behaviour_weight
  amount_weight   = sqrt(balance / largest_open_balance)     # diminishing returns
  bucket_weight   = 1.0 / 1.5 / 2.0 / 2.5 / 3.0             # current → 90+
  behaviour_weight= 1.15 if customer paid late before else 1.0
  score_pct       = 100 × score / max(score in run)         # comparable across days
  ```

  The sqrt keeps a $10k debt from burying a $1k debt that is 200 days late;
  the test suite pins that behavior.
- Aggregates: bucket totals/counts, customer exposure (with oldest overdue
  days), outstanding/overdue totals, overdue ratio, average days to pay,
  per-currency totals for mixed-currency files.
- `chase_list(top)` sorts by score, then balance, then invoice number — a
  total order, so reports are reproducible.

### report.py — `AgingReport` → text

- **Markdown** — header stats, bucket table, customer exposure table, chase
  list, and an explicit "software output, not financial advice" line.
- **CSV** — the chase list with every scoring input (`bucket`, `balance`,
  `score_pct`, `late_history`) so it can be re-sorted or mail-merged.
- **HTML** — a single file with inline CSS: summary cards, bucket bars
  (scaled to the largest bucket), the chase table with bucket pills, and the
  late-payer list. No external assets, no JavaScript — it opens from disk and
  survives being emailed as an attachment.

### cli.py — commands and exit codes

| Command | Purpose | Exit |
|---|---|---|
| `report FILE` | render the aging report | 0, or 1 if `--fail-overdue-ratio` trips |
| `check FILE` | validate input, print counts | 0 / 2 |

Exit 2 covers every input problem (missing file, missing columns, bad date,
bad amount, wrong field count, bad `--as-of`). stdout/stderr are reconfigured
to UTF-8 with `errors="replace"` so currency symbols cannot crash a Windows
console.

## Failure handling

| Failure | Behavior |
|---|---|
| file missing / empty | `InputError` → stderr + exit 2 |
| missing required columns | lists the missing names |
| bad date/amount in row N | `file:N: cannot parse …` |
| row wider than header | `file:N: row has X fields but the header declares Y` |
| empty ledger | report renders with zeros (tested) |

## Testing strategy

- **model**: money formats (US/EU/negatives/minor units), six date formats,
  status dispositions, balance math including overpayment, CSV errors with
  line numbers, BOM, blank lines, optional-column defaults.
- **aging**: bucket boundary table, weight monotonicity, partition counts,
  bucket totals, outstanding/overdue/ratio, behaviour weights from history,
  chase ordering, 0–100 scaling, customer exposure, average days to pay,
  multi-currency totals, determinism, and the "small old debt outranks big
  recent debt" property.
- **report/CLI**: markdown/csv/html shapes, `--top` limits, the
  `--fail-overdue-ratio` gate (1 and 0), usage errors, `--as-of` default,
  demo-summary JSON validity, byte-identical reruns.