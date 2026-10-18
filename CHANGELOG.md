# Changelog

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versions follow [Semantic Versioning](https://semver.org/).

## [0.1.0] - 2026-10-18

### Added

- CSV loader with header normalization, required-column validation,
  line-accurate error messages (including rows wider than the header), BOM
  tolerance and blank-line skipping.
- Integer-cent money handling with US/European formats, accounting negatives
  and per-currency minor units (JPY/KRW 0, BHD/KWD 3 …).
- Aging buckets (current, 1–30, 31–60, 61–90, 90+) with counts and balances.
- Explainable chase score (amount × bucket × behaviour, scaled 0–100) and a
  total-ordered chase list.
- Customer exposure table with oldest-overdue days and late-payment history.
- Markdown, CSV and standalone HTML report renderers.
- `agingradar report` (`--as-of`, `--format`, `-o`, `--top`,
  `--fail-overdue-ratio`) and `agingradar check`.
- 16-invoice sample fixture, deterministic demo (`examples/demo.py`),
  55 tests, CI workflow.