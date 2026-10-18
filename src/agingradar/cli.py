"""agingradar CLI: aging report from an invoices CSV."""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path
from typing import Sequence

from .aging import build_report, summarize_currency
from .model import InputError, load_csv, parse_date
from .report import render_chase_csv, render_html, render_markdown

EXIT_OK = 0
EXIT_FINDINGS = 1  # reserved: unused for now (report always succeeds)
EXIT_USAGE = 2

for _stream in (sys.stdout, sys.stderr):
    # reports contain currency symbols and em dashes; keep Windows consoles usable
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except (AttributeError, OSError):  # pragma: no cover - exotic streams
        pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agingradar",
        description="Invoice aging buckets, chase priority and dunning reports from a CSV.",
    )
    parser.add_argument("--version", action="version", version="agingradar 0.1.0")
    sub = parser.add_subparsers(dest="command", required=True)

    rep = sub.add_parser("report", help="build the aging report")
    rep.add_argument("csv_file", help="invoices CSV (number,customer,issue_date,due_date,amount,...)")
    rep.add_argument("--as-of", default=None, help="report date, YYYY-MM-DD (default: today)")
    rep.add_argument("--format", choices=["markdown", "html", "csv"], default="markdown")
    rep.add_argument("-o", "--output", help="write to file (default: stdout)")
    rep.add_argument("--top", type=int, default=10, help="chase list length (default 10)")
    rep.add_argument("--fail-overdue-ratio", type=float, default=None,
                     help="exit 1 when the overdue share of outstanding exceeds this (e.g. 0.5)")

    chk = sub.add_parser("check", help="validate the CSV without producing a report")
    chk.add_argument("csv_file")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    try:
        ledger = load_csv(args.csv_file)
        raw_as_of = getattr(args, "as_of", None)
        as_of = parse_date(raw_as_of) if raw_as_of else date.today()
    except InputError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE

    report = build_report(ledger, as_of=as_of)

    if args.command == "check":
        print(
            f"{args.csv_file}: OK — {len(ledger.invoices)} invoices, "
            f"{len(ledger.customers)} customer(s), currency {summarize_currency(ledger)}, "
            f"as of {as_of.isoformat()}"
        )
        return EXIT_OK

    if args.format == "markdown":
        text = render_markdown(report, top=args.top)
    elif args.format == "html":
        text = render_html(report, top=args.top)
    else:
        text = render_chase_csv(report, top=args.top if args.top > 0 else None)

    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"wrote {args.output}")
    else:
        print(text, end="")

    if args.fail_overdue_ratio is not None and report.overdue_ratio() > args.fail_overdue_ratio:
        print(
            f"overdue ratio {report.overdue_ratio():.0%} exceeds the gate of {args.fail_overdue_ratio:.0%}",
            file=sys.stderr,
        )
        return 1
    return EXIT_OK


def entry() -> None:  # pragma: no cover
    raise SystemExit(main())


if __name__ == "__main__":  # pragma: no cover
    entry()