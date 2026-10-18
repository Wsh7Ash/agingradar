# Contributing

Thanks for helping improve agingradar.

## Setup

```shell
python -m venv .venv && source .venv/bin/activate
pip install -e .
python -m unittest discover -s tests -t . -v
python examples/demo.py
```

Standard library only — agingradar should stay dependency-free so a
bookkeeper can run it anywhere Python exists.

## Ground rules

1. **Money is integer cents.** No floats in balances, totals or comparisons —
   ever.
2. **Errors name file:line.** Input problems must stay traceable to the row
   that caused them.
3. **The score stays explainable.** Any change to scoring must keep every
   component visible in the report and documented in README/ARCHITECTURE.
4. **Determinism.** Same CSV + same `--as-of` = byte-identical output. No
   timestamps, no randomness, no locale-dependent formatting.
5. **Non-developer readers first.** Reports are for bookkeepers: plain
   language, no jargon, no hidden state.

## Adding a feature

1. Tests first (positive **and** negative case; boundary values for money and
   dates).
2. Update README (flags table, limitations) and CHANGELOG.
3. Keep `examples/demo.py` honest — if the demo's sanity checks no longer
   describe the behavior, fix them, don't delete them.

## Commit style

Any clear imperative message is fine; reference the issue when there is one.