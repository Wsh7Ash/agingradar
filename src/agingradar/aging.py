"""Aging buckets and chase-priority scoring.

Buckets follow the common bookkeeping convention:

    current (not yet due) · 1–30 · 31–60 · 61–90 · 90+ days overdue

The chase score is deliberately explainable — every invoice gets the same
three visible components, so a bookkeeper can argue with the number instead
of trusting it:

    score = amount weight × bucket weight × behaviour weight

* **amount weight** — sqrt of the balance relative to the largest open balance
  (big debts matter more, but a small debt in 90+ still outranks a big one
  that is merely late).
* **bucket weight** — 1.0 current, 1.5 (1–30), 2.0 (31–60), 2.5 (61–90),
  3.0 (90+).
* **behaviour weight** — 1.15 if this customer has paid late before (any
  historical invoice paid ≥ 1 day after due), 1.0 otherwise.

Scores are scaled to 0–100 against the highest score in the run so the report
is comparable across days.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date

from .model import Invoice, Ledger, format_money

BUCKETS: tuple[tuple[str, int, int | None], ...] = (
    ("current", -10**6, 0),
    ("1-30", 1, 30),
    ("31-60", 31, 60),
    ("61-90", 61, 90),
    ("90+", 91, None),
)

BUCKET_WEIGHTS = {"current": 1.0, "1-30": 1.5, "31-60": 2.0, "61-90": 2.5, "90+": 3.0}

LATE_THRESHOLD_DAYS = 0


def bucket_for(days_overdue: int) -> str:
    if days_overdue <= 0:
        return "current"
    for name, low, high in BUCKETS:
        if name == "current":
            continue
        if days_overdue >= low and (high is None or days_overdue <= high):
            return name
    return "90+"  # pragma: no cover - unreachable


@dataclass
class AgingRow:
    invoice: Invoice
    days_overdue: int
    bucket: str
    amount_weight: float = 0.0
    behaviour_weight: float = 1.0
    score: float = 0.0
    score_pct: int = 0
    late_history: bool = False

    @property
    def balance_cents(self) -> int:
        return self.invoice.balance_cents


@dataclass
class AgingReport:
    as_of: date
    source: str = "<memory>"
    rows: list[AgingRow] = field(default_factory=list)
    ignored: list[Invoice] = field(default_factory=list)
    paid_in_period: list[Invoice] = field(default_factory=list)
    late_payers: dict[str, int] = field(default_factory=dict)

    @property
    def open_rows(self) -> list[AgingRow]:
        return [r for r in self.rows if r.invoice.is_open]

    def bucket_totals(self) -> dict[str, int]:
        totals = {name: 0 for name, _, _ in BUCKETS}
        for row in self.open_rows:
            totals[row.bucket] += row.balance_cents
        return totals

    def bucket_counts(self) -> dict[str, int]:
        counts = {name: 0 for name, _, _ in BUCKETS}
        for row in self.open_rows:
            counts[row.bucket] += 1
        return counts

    def customer_totals(self) -> dict[str, dict[str, int]]:
        out: dict[str, dict[str, int]] = {}
        for row in self.open_rows:
            entry = out.setdefault(row.invoice.customer, {"total": 0, "overdue": 0, "oldest_days": 0})
            entry["total"] += row.balance_cents
            if row.days_overdue > 0:
                entry["overdue"] += row.balance_cents
                entry["oldest_days"] = max(entry["oldest_days"], row.days_overdue)
        return out

    def total_outstanding(self) -> int:
        return sum(r.balance_cents for r in self.open_rows)

    def total_overdue(self) -> int:
        return sum(r.balance_cents for r in self.open_rows if r.days_overdue > 0)

    def overdue_ratio(self) -> float:
        total = self.total_outstanding()
        return (self.total_overdue() / total) if total else 0.0

    def chase_list(self, top: int | None = None) -> list[AgingRow]:
        rows = sorted(self.open_rows, key=lambda r: (-r.score, -r.balance_cents, r.invoice.number))
        return rows[:top] if top else rows

    def average_days_to_pay(self) -> float | None:
        values = [
            (inv.paid_date - inv.due_date).days
            for inv in self.paid_in_period
            if inv.paid_date is not None
        ]
        values = [v for v in values]
        if not values:
            return None
        return sum(values) / len(values)


def _late_payer_map(ledger: Ledger) -> dict[str, int]:
    """Map customer → number of invoices paid at least one day after due."""
    out: dict[str, int] = {}
    for inv in ledger.invoices:
        if inv.paid_date is None:
            continue
        late_days = (inv.paid_date - inv.due_date).days
        if late_days >= 1:
            out[inv.customer] = out.get(inv.customer, 0) + 1
    return out


def build_report(ledger: Ledger, as_of: date | None = None, ignore_paid: bool = True) -> AgingReport:
    as_of = as_of or date.today()
    report = AgingReport(as_of=as_of, source=ledger.source)
    report.late_payers = _late_payer_map(ledger)

    for inv in ledger.invoices:
        if inv.is_ignored:
            report.ignored.append(inv)
            continue
        if inv.fully_paid:
            report.paid_in_period.append(inv)
            if not ignore_paid:
                pass  # paid invoices never enter the aging table
            continue
        days = inv.days_overdue(as_of)
        row = AgingRow(
            invoice=inv,
            days_overdue=days,
            bucket=bucket_for(days),
            late_history=report.late_payers.get(inv.customer, 0) > 0,
            behaviour_weight=1.15 if report.late_payers.get(inv.customer, 0) > 0 else 1.0,
        )
        report.rows.append(row)

    _score(report)
    return report


def _score(report: AgingReport) -> None:
    open_rows = [r for r in report.rows if r.invoice.is_open]
    max_balance = max((r.balance_cents for r in open_rows), default=0)
    for row in open_rows:
        if max_balance > 0:
            row.amount_weight = math.sqrt(row.balance_cents / max_balance)
        row.score = row.amount_weight * BUCKET_WEIGHTS[row.bucket] * row.behaviour_weight
    top = max((r.score for r in open_rows), default=0.0)
    for row in open_rows:
        row.score_pct = int(round(100 * row.score / top)) if top > 0 else 0


def summarize_currency(ledger: Ledger) -> str:
    currencies = sorted({i.currency for i in ledger.invoices})
    if len(currencies) != 1:
        return f"mixed ({', '.join(currencies)})"
    return currencies[0]


def totals_by_currency(report: AgingReport) -> dict[str, int]:
    out: dict[str, int] = {}
    for row in report.open_rows:
        out[row.invoice.currency] = out.get(row.invoice.currency, 0) + row.balance_cents
    return out


def render_totals(report: AgingReport) -> str:
    totals = totals_by_currency(report)
    return ", ".join(f"{format_money(v, c)} ({c})" for c, v in sorted(totals.items())) or "0"