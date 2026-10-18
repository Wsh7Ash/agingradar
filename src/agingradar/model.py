"""Invoice model, integer-cent money math, and CSV loading.

Money is always handled as **integer cents** (or the smallest unit of the
declared currency) — floating point has no place in an aging report.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

CURRENCY_DEFAULT = "USD"

# ISO-4217 minor-unit exponents for the currencies the sample data uses.
MINOR_UNITS = {"JPY": 0, "KRW": 0, "USD": 2, "EUR": 2, "GBP": 2, "CAD": 2, "AUD": 2, "INR": 2, "BHD": 3, "KWD": 3}

OPEN_STATUSES = {"open", "unpaid", "sent", "overdue", "due"}
PAID_STATUSES = {"paid", "settled", "closed"}
IGNORED_STATUSES = {"void", "cancelled", "canceled", "draft", "credit_note"}


class InputError(ValueError):
    """Raised for unusable CSV input."""


@dataclass
class Invoice:
    number: str
    customer: str
    issue_date: date
    due_date: date
    amount_cents: int          # original invoice amount
    paid_cents: int = 0        # payments applied so far
    currency: str = CURRENCY_DEFAULT
    status: str = "open"
    paid_date: date | None = None

    @property
    def balance_cents(self) -> int:
        return max(0, self.amount_cents - self.paid_cents)

    @property
    def is_open(self) -> bool:
        return self.status in OPEN_STATUSES and self.balance_cents > 0

    @property
    def fully_paid(self) -> bool:
        return self.status in PAID_STATUSES or (self.amount_cents > 0 and self.balance_cents == 0)

    @property
    def is_ignored(self) -> bool:
        return self.status in IGNORED_STATUSES

    def days_overdue(self, as_of: date) -> int:
        return (as_of - self.due_date).days

    def days_late_for_payment(self) -> int | None:
        """Days between due date and payment date; None when never paid."""
        if self.paid_date is None:
            return None
        return (self.paid_date - self.due_date).days


@dataclass
class Ledger:
    invoices: list[Invoice] = field(default_factory=list)
    source: str = "<memory>"

    @property
    def customers(self) -> list[str]:
        return sorted({i.customer for i in self.invoices})


def parse_money(raw: str, currency: str = CURRENCY_DEFAULT) -> int:
    """Parse '$1,234.56' / '1234.56' / '1234,56' into integer minor units."""
    if raw is None:
        return 0
    text = str(raw).strip()
    if not text:
        return 0
    text = text.replace("$", "").replace("€", "").replace("£", "").strip()
    negative = text.startswith("(") and text.endswith(")")
    if negative:
        text = text[1:-1]
    text = text.replace(" ", "")
    # European decimal comma, e.g. 1.234,56 or 1234,56
    if re.fullmatch(r"\d{1,3}(\.\d{3})+,\d{1,2}", text) or re.fullmatch(r"\d+,\d{1,2}", text):
        text = text.replace(".", "").replace(",", ".")
    else:
        text = text.replace(",", "")
    try:
        value = Decimal(text)
    except InvalidOperation as exc:
        raise InputError(f"cannot parse money value {raw!r}") from exc
    exponent = MINOR_UNITS.get(currency.upper(), 2)
    scaled = value * (Decimal(10) ** exponent)
    cents = int(scaled.to_integral_value())
    return -cents if negative else cents


def format_money(cents: int, currency: str = CURRENCY_DEFAULT) -> str:
    exponent = MINOR_UNITS.get(currency.upper(), 2)
    sign = "-" if cents < 0 else ""
    cents = abs(cents)
    if exponent == 0:
        return f"{sign}{symbol(currency)}{cents:,}"
    unit = 10 ** exponent
    whole, frac = divmod(cents, unit)
    return f"{sign}{symbol(currency)}{whole:,}.{frac:0{exponent}d}"


def symbol(currency: str) -> str:
    return {"USD": "$", "EUR": "€", "GBP": "£", "JPY": "¥", "CAD": "C$", "AUD": "A$", "INR": "₹"}.get(currency.upper(), "")


def parse_date(raw: str) -> date:
    text = (raw or "").strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%Y/%m/%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise InputError(f"cannot parse date {raw!r} (use YYYY-MM-DD)")


REQUIRED_COLUMNS = {"number", "customer", "issue_date", "due_date", "amount"}


def load_csv(path: str | Path) -> Ledger:
    p = Path(path)
    if not p.exists():
        raise InputError(f"file not found: {p}")
    with p.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            raise InputError(f"{p}: empty file")
        headers = {h.strip().lower().replace(" ", "_") for h in reader.fieldnames}
        missing = REQUIRED_COLUMNS - headers
        if missing:
            raise InputError(f"{p}: missing column(s): {', '.join(sorted(missing))}")
        invoices: list[Invoice] = []
        for line_no, row in enumerate(reader, start=2):
            if None in row:
                extras = row[None]
                raise InputError(
                    f"{p}:{line_no}: row has {len(extras) + len(reader.fieldnames or [])} "
                    f"fields but the header declares {len(reader.fieldnames or [])}"
                )
            norm = {(k or "").strip().lower().replace(" ", "_"): (v or "").strip() for k, v in row.items()}
            if not norm.get("number") and not norm.get("customer"):
                continue  # blank line
            try:
                currency = (norm.get("currency") or CURRENCY_DEFAULT).upper()
                amount = parse_money(norm["amount"], currency)
                status = (norm.get("status") or "open").lower()
                paid_raw = norm.get("paid_amount") or norm.get("paid") or "0"
                paid = parse_money(paid_raw, currency) if paid_raw else 0
                paid_date_raw = norm.get("paid_date") or ""
                paid_date = parse_date(paid_date_raw) if paid_date_raw else None
                invoices.append(
                    Invoice(
                        number=norm["number"] or f"line-{line_no}",
                        customer=norm["customer"],
                        issue_date=parse_date(norm["issue_date"]),
                        due_date=parse_date(norm["due_date"]),
                        amount_cents=amount,
                        paid_cents=paid,
                        currency=currency,
                        status=status,
                        paid_date=paid_date,
                    )
                )
            except (KeyError, InputError) as exc:
                raise InputError(f"{p}:{line_no}: {exc}") from exc
    if not invoices:
        raise InputError(f"{p}: no invoice rows found")
    return Ledger(invoices=invoices, source=str(p))