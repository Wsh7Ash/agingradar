# Results

Honest record of what was actually executed for agingradar on 2026-10-18.

## Environment

- OS: Windows 11 (MINGW64_NT-10.0-19044, x86_64), MSYS2 MinGW shell
- Runtime: Python 3.14.3 (project venv `.venv/`), pip 25.3
- Dependency manager: pip (`python -m venv .venv` + `.venv/bin/python -m pip install -e .`)
- Network: none — the package performs no network I/O and none was needed

## Validation performed

| Gate | Result | Evidence |
|---|---|---|
| install | **PASS** | venv + `pip install -e .` → exit 0; `.venv/bin/agingradar --version` → `agingradar 0.1.0` (system MSYS pip is PEP-668 managed, hence the venv) |
| build | N/A | pure Python, no build step |
| unit tests | **PASS** | `python -m unittest discover -s tests -t .` → `Ran 55 tests … OK`, exit 0 |
| unit tests (warnings as errors) | **PASS** | `python -W error::ResourceWarning -m unittest discover -s tests -t .` → 55 tests OK |
| integration tests | **PASS** | included in the 55: CLI runs against the real fixture (markdown/html/csv/check/gates) |
| lint | N/A | no linter configured for this repo |
| type check | N/A | no type checker configured; annotations present but not mypy-verified |
| demo run | **PASS** | `python examples/demo.py` → all 7 sanity checks `[ok]`, exit 0 |
| CLI gate check | **PASS** | `--fail-overdue-ratio 0.5` → exit 1; `0.999` → exit 0 (asserted in `tests/test_report_and_cli.py`) |
| secret scan | **PASS** | grep for credential/key/token patterns: only prose matched; no `.env`, no key material, no real customer data (the fixture is fictional) |

## Commands executed

```shell
python -m venv .venv
.venv/bin/python -m pip install -e .
python -m unittest discover -s tests -t . -v     # 55 tests, OK, exit 0
python -W error::ResourceWarning -m unittest discover -s tests -t .
.venv/bin/agingradar --version                    # agingradar 0.1.0
.venv/bin/agingradar check examples/invoices-sample.csv
.venv/bin/agingradar report examples/invoices-sample.csv --as-of 2026-10-18
.venv/bin/agingradar report examples/invoices-sample.csv --as-of 2026-10-18 --fail-overdue-ratio 0.5  # exit 1
python examples/demo.py                           # exit 0
```

## Observed result

`python examples/demo.py` (deterministic, as-of 2026-10-18):

```
[ok] bucket math
[ok] partial payment reduces balance
[ok] void/draft excluded
[ok] paid excluded
[ok] late payers detected
[ok] chase list is score-ordered
[ok] oldest invoice in 90+ bucket
[done] 16 invoices -> outstanding 7631.75, overdue 7291.75 (96%)
[done] results/ written (aging-report.md, aging-report.html, chase-list.csv, demo-summary.json)
DEMO_EXIT=0
```

Head of the generated markdown report:

```
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

## Chase list (top 10)
| # | Invoice | Customer | Due | Days | Bucket | Balance | Score |
| 1 | INV-1005 | Cedar Design Studio | 2026-03-31 | +201 | 90+ | $2,400.00 | 100 |
| 2 | INV-1001 | Acme Bakery | 2026-07-31 | +79 | 61-90 | $1,250.00 | 69 |
| 3 | INV-1014 | Cedar Design Studio | 2026-06-14 | +126 | 90+ | $1,050.00 | 66 |
```

Behavior proven by tests, not just by the demo:

- bucket boundaries at 0/1/30/31/60/61/90/91 days and the weight ladder
- a **small, very old debt outranks a big, recently due one** (sqrt amount ×
  bucket weights) — pinned by an explicit test
- partial payments reduce the balance (never below zero); void/draft/paid rows
  are excluded from aging but kept in the right summary lists
- late-payment history raises the score by exactly 15% and shows as ⚠
- money formats: `$1,234.56`, `1234,56`, `1.234,56`, `(50.00)`, JPY/BHD
  minor units; multi-currency totals stay per currency
- CSV errors carry `file:line`, including rows wider than the header
- CLI: markdown/html/csv output, `-o`, `--top`, `--as-of` default, both
  overdue-ratio gate outcomes, usage errors

## Generated artifacts

- `results/aging-report.md` — markdown aging report (as-of 2026-10-18)
- `results/aging-report.html` — standalone HTML page (inline CSS, no scripts)
- `results/chase-list.csv` — chase list with all scoring inputs
- `results/demo-summary.json` — machine-readable summary of the run

Regenerate with `python examples/demo.py`.

## Known limitations

- No linter/type checker ran (none configured). CI covers Python 3.10/3.12;
  this local run used 3.14.3.
- The fixture uses fictional customers; amounts and dates were authored for
  this repository, not exported from any real business.
- The demo pins `--as-of 2026-10-18`, so regenerated artifacts are byte-stable;
  a run with today's date will (correctly) show different bucket counts.
- Average days-to-payment only covers invoices with a `paid_date` column.