"""Aging tests: buckets, scoring, aggregates, chase ordering."""

from __future__ import annotations

import unittest
from datetime import date

from agingradar.aging import BUCKET_WEIGHTS, bucket_for, build_report
from agingradar.model import Invoice, Ledger

AS_OF = date(2026, 10, 18)


def inv(number, customer, due, amount, paid=0, paid_date=None, status="open", currency="USD"):
    return Invoice(
        number=number,
        customer=customer,
        issue_date=date(2026, 1, 1),
        due_date=due,
        amount_cents=amount,
        paid_cents=paid,
        paid_date=paid_date,
        status=status,
        currency=currency,
    )


class BucketTests(unittest.TestCase):
    def test_boundaries(self) -> None:
        cases = {0: "current", -5: "current", 1: "1-30", 30: "1-30", 31: "31-60",
                 60: "31-60", 61: "61-90", 90: "61-90", 91: "90+", 400: "90+"}
        for days, expected in cases.items():
            self.assertEqual(bucket_for(days), expected, days)

    def test_weights_increase_with_age(self) -> None:
        ordered = [BUCKET_WEIGHTS[name] for name in ("current", "1-30", "31-60", "61-90", "90+")]
        self.assertEqual(ordered, sorted(ordered))
        self.assertGreater(ordered[-1], ordered[0])


class ReportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ledger = Ledger(
            invoices=[
                # 201 days overdue, biggest balance -> top chase
                inv("A", "Cedar", date(2026, 3, 31), 240000),
                # 79 days overdue, medium, from a customer with late history
                inv("B", "Acme", date(2026, 7, 31), 125000),
                # historical: paid 20 days late -> gives Acme its late history
                inv("Bhist", "Acme", date(2026, 5, 31), 48000, paid=48000,
                    paid_date=date(2026, 6, 20), status="paid"),
                # not yet due -> current bucket
                inv("C", "Acme", date(2026, 11, 30), 34000),
                # fully paid 2 days early -> excluded from aging
                inv("D", "Acme", date(2026, 9, 30), 150000, paid=150000,
                    paid_date=date(2026, 9, 28), status="paid"),
                # void -> ignored
                inv("E", "Blue", date(2026, 1, 15), 14000, status="void"),
                # partial payment, 43 days overdue -> 31-60
                inv("F", "Blue", date(2026, 9, 5), 89000, paid=30000),
            ]
        )
        self.report = build_report(self.ledger, as_of=AS_OF)

    def test_partitions(self) -> None:
        self.assertEqual(len(self.report.rows), 4)      # A, B, C, F
        self.assertEqual(len(self.report.paid_in_period), 2)  # Bhist, D
        self.assertEqual(len(self.report.ignored), 1)

    def test_bucket_totals(self) -> None:
        totals = self.report.bucket_totals()
        self.assertEqual(totals["90+"], 240000)
        self.assertEqual(totals["61-90"], 125000)
        self.assertEqual(totals["current"], 34000)
        self.assertEqual(totals["31-60"], 59000)  # F balance after partial payment

    def test_outstanding_and_overdue(self) -> None:
        self.assertEqual(self.report.total_outstanding(), 240000 + 125000 + 34000 + 59000)
        self.assertEqual(self.report.total_overdue(), 240000 + 125000 + 59000)
        self.assertAlmostEqual(self.report.overdue_ratio(), (240000 + 125000 + 59000) / (240000 + 125000 + 34000 + 59000))

    def test_late_payer_behaviour_weight(self) -> None:
        rows = {r.invoice.number: r for r in self.report.rows}
        self.assertTrue(rows["B"].late_history)          # paid late
        self.assertFalse(rows["A"].late_history)
        self.assertEqual(rows["B"].behaviour_weight, 1.15)
        self.assertEqual(rows["A"].behaviour_weight, 1.0)

    def test_chase_list_is_score_ordered(self) -> None:
        scores = [r.score for r in self.report.chase_list()]
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertEqual(self.report.chase_list()[0].invoice.number, "A")
        self.assertEqual(self.report.chase_list(2)[0].invoice.number, "A")
        self.assertEqual(len(self.report.chase_list(2)), 2)

    def test_scores_are_scaled_to_100(self) -> None:
        top = self.report.chase_list()[0]
        self.assertEqual(top.score_pct, 100)
        for row in self.report.open_rows:
            self.assertGreaterEqual(row.score_pct, 0)
            self.assertLessEqual(row.score_pct, 100)

    def test_customer_totals_and_oldest(self) -> None:
        totals = self.report.customer_totals()
        self.assertIn("Cedar", totals)
        self.assertEqual(totals["Cedar"]["oldest_days"], 201)
        self.assertEqual(totals["Acme"]["total"], 125000 + 34000)

    def test_average_days_to_pay(self) -> None:
        # Bhist paid 20 days late, D paid 2 days early -> (20 - 2) / 2 = 9.0
        self.assertAlmostEqual(self.report.average_days_to_pay(), 9.0)

    def test_empty_ledger_is_safe(self) -> None:
        report = build_report(Ledger(invoices=[]), as_of=AS_OF)
        self.assertEqual(report.total_outstanding(), 0)
        self.assertEqual(report.overdue_ratio(), 0.0)
        self.assertEqual(report.chase_list(), [])
        self.assertIsNone(report.average_days_to_pay())

    def test_multi_currency_totals(self) -> None:
        ledger = Ledger(invoices=[
            inv("X", "JP", date(2026, 9, 1), 500000, currency="JPY"),
            inv("Y", "EU", date(2026, 9, 1), 10000, currency="EUR"),
        ])
        report = build_report(ledger, as_of=AS_OF)
        self.assertEqual(report.total_outstanding(), 510000)
        from agingradar.aging import totals_by_currency
        self.assertEqual(totals_by_currency(report), {"EUR": 10000, "JPY": 500000})

    def test_deterministic_scoring(self) -> None:
        again = build_report(self.ledger, as_of=AS_OF)
        self.assertEqual(
            [r.score for r in self.report.chase_list()],
            [r.score for r in again.chase_list()],
        )

    def test_smaller_old_debt_beats_bigger_recent_one(self) -> None:
        ledger = Ledger(invoices=[
            inv("OLD", "A", date(2026, 1, 1), 100000),   # 90+, $1,000
            inv("NEW", "B", date(2026, 10, 1), 300000),  # 1-30, $3,000
        ])
        report = build_report(ledger, as_of=AS_OF)
        rows = report.chase_list()
        # amount weight of NEW (sqrt(3)) * 1.5 = 2.6; OLD sqrt(1) * 3.0 = 3.0
        self.assertEqual(rows[0].invoice.number, "OLD")


if __name__ == "__main__":
    unittest.main()