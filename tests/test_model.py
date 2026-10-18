"""Model tests: money math, dates, CSV loading."""

from __future__ import annotations

import os
import tempfile
import unittest
from datetime import date

from agingradar.model import (
    InputError,
    Invoice,
    format_money,
    load_csv,
    parse_date,
    parse_money,
)

EXAMPLE_CSV = os.path.join(os.path.dirname(__file__), "..", "examples", "invoices-sample.csv")


class MoneyTests(unittest.TestCase):
    def test_us_formats(self) -> None:
        self.assertEqual(parse_money("$1,234.56"), 123456)
        self.assertEqual(parse_money("1234.56"), 123456)
        self.assertEqual(parse_money("100"), 10000)

    def test_european_formats(self) -> None:
        self.assertEqual(parse_money("1.234,56"), 123456)
        self.assertEqual(parse_money("1234,56"), 123456)

    def test_parenthesised_negative(self) -> None:
        self.assertEqual(parse_money("(50.00)"), -5000)

    def test_zero_and_empty(self) -> None:
        self.assertEqual(parse_money("0"), 0)
        self.assertEqual(parse_money(""), 0)
        self.assertEqual(parse_money("  "), 0)

    def test_currency_exponent(self) -> None:
        self.assertEqual(parse_money("1000", "JPY"), 1000)
        self.assertEqual(parse_money("1.234", "BHD"), 1234)

    def test_invalid_money_raises(self) -> None:
        with self.assertRaises(InputError):
            parse_money("not-a-number")

    def test_format_money(self) -> None:
        self.assertEqual(format_money(123456), "$1,234.56")
        self.assertEqual(format_money(-5000), "-$50.00")
        self.assertEqual(format_money(1000, "JPY"), "¥1,000")
        self.assertEqual(format_money(1234, "BHD"), "1.234")


class DateTests(unittest.TestCase):
    def test_iso(self) -> None:
        self.assertEqual(parse_date("2026-10-18"), date(2026, 10, 18))

    def test_day_first(self) -> None:
        self.assertEqual(parse_date("31/05/2026"), date(2026, 5, 31))

    def test_invalid_date_raises(self) -> None:
        with self.assertRaises(InputError):
            parse_date("tomorrow")


class InvoiceTests(unittest.TestCase):
    def _inv(self, **kwargs) -> Invoice:
        base = dict(
            number="INV-1", customer="Acme", issue_date=date(2026, 1, 1),
            due_date=date(2026, 1, 31), amount_cents=10000,
        )
        base.update(kwargs)
        return Invoice(**base)

    def test_balance_and_payment(self) -> None:
        inv = self._inv(paid_cents=4000)
        self.assertEqual(inv.balance_cents, 6000)
        self.assertFalse(inv.fully_paid)
        paid = self._inv(paid_cents=10000, status="paid", paid_date=date(2026, 2, 5))
        self.assertEqual(paid.balance_cents, 0)
        self.assertTrue(paid.fully_paid)

    def test_overpayment_never_goes_negative(self) -> None:
        self.assertEqual(self._inv(paid_cents=12000).balance_cents, 0)

    def test_open_and_ignored_statuses(self) -> None:
        self.assertTrue(self._inv(status="open").is_open)
        self.assertTrue(self._inv(status="overdue").is_open)
        self.assertFalse(self._inv(status="void").is_open)
        self.assertTrue(self._inv(status="void").is_ignored)
        self.assertTrue(self._inv(status="draft").is_ignored)

    def test_days_overdue_and_days_late(self) -> None:
        inv = self._inv(due_date=date(2026, 1, 31), paid_date=date(2026, 2, 10))
        self.assertEqual(inv.days_overdue(date(2026, 3, 1)), 29)
        self.assertEqual(inv.days_late_for_payment(), 10)
        self.assertIsNone(self._inv().days_late_for_payment())


class CsvTests(unittest.TestCase):
    def test_sample_fixture_loads(self) -> None:
        ledger = load_csv(EXAMPLE_CSV)
        self.assertEqual(len(ledger.invoices), 16)
        self.assertEqual(len(ledger.customers), 5)
        currencies = {i.currency for i in ledger.invoices}
        self.assertEqual(currencies, {"USD"})

    def test_missing_file_raises(self) -> None:
        with self.assertRaises(InputError):
            load_csv("/no/such/file.csv")

    def test_missing_columns_raise(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "bad.csv")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("number,amount\nINV-1,10\n")
            with self.assertRaises(InputError) as ctx:
                load_csv(path)
            self.assertIn("missing column", str(ctx.exception))

    def test_bad_row_reports_line_number(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "bad.csv")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(
                    "number,customer,issue_date,due_date,amount\n"
                    "INV-1,Acme,2026-01-01,2026-01-31,10.00\n"
                    "INV-2,Acme,2026-01-01,not-a-date,10.00\n"
                )
            with self.assertRaises(InputError) as ctx:
                load_csv(path)
            self.assertIn(":3:", str(ctx.exception))

    def test_row_with_too_many_fields_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "wide.csv")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(
                    "number,customer,issue_date,due_date,amount\n"
                    "INV-1,Acme,2026-01-01,2026-01-31,10.00,extra,more\n"
                )
            with self.assertRaises(InputError) as ctx:
                load_csv(path)
            self.assertIn("fields but the header", str(ctx.exception))

    def test_blank_lines_are_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "blank.csv")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(
                    "number,customer,issue_date,due_date,amount\n"
                    ",,,,\n"
                    "INV-1,Acme,2026-01-01,2026-01-31,10.00\n"
                )
            self.assertEqual(len(load_csv(path).invoices), 1)

    def test_optional_columns_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "min.csv")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(
                    "number,customer,issue_date,due_date,amount\n"
                    "INV-1,Acme,2026-01-01,2026-01-31,10.00\n"
                )
            inv = load_csv(path).invoices[0]
            self.assertEqual(inv.status, "open")
            self.assertEqual(inv.paid_cents, 0)
            self.assertIsNone(inv.paid_date)
            self.assertEqual(inv.currency, "USD")

    def test_bom_is_tolerated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "bom.csv")
            with open(path, "w", encoding="utf-8-sig") as fh:
                fh.write(
                    "number,customer,issue_date,due_date,amount\n"
                    "INV-1,Acme,2026-01-01,2026-01-31,10.00\n"
                )
            self.assertEqual(load_csv(path).invoices[0].number, "INV-1")


if __name__ == "__main__":
    unittest.main()