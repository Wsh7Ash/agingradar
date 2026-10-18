"""Renderer and CLI tests."""

from __future__ import annotations

import contextlib
import csv
import io
import json
import os
import tempfile
import unittest
from datetime import date

from agingradar.aging import build_report
from agingradar.model import Invoice, Ledger
from agingradar.report import render_chase_csv, render_html, render_markdown

EXAMPLE_CSV = os.path.join(os.path.dirname(__file__), "..", "examples", "invoices-sample.csv")
AS_OF = date(2026, 10, 18)


def sample_report(top=10):
    from agingradar.model import load_csv

    return build_report(load_csv(EXAMPLE_CSV), as_of=AS_OF)


class MarkdownTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = render_markdown(sample_report(), top=5)

    def test_header_and_totals(self) -> None:
        self.assertIn("# Aging report — 2026-10-18", self.text)
        self.assertIn("outstanding:", self.text)
        self.assertIn("overdue:", self.text)

    def test_tables_present(self) -> None:
        for heading in ("## Aging buckets", "## Top customers by exposure", "## Chase list"):
            self.assertIn(heading, self.text)
        self.assertIn("| current |", self.text)
        self.assertIn("| 90+ |", self.text)

    def test_chase_list_respects_top(self) -> None:
        rows = [line for line in self.text.splitlines() if line.startswith("| ") and "INV-" in line]
        self.assertEqual(len(rows), 5)

    def test_disclaimer_present(self) -> None:
        self.assertIn("not financial advice", self.text)


class CsvRenderTests(unittest.TestCase):
    def test_chase_csv_shape(self) -> None:
        text = render_chase_csv(sample_report())
        reader = csv.reader(io.StringIO(text))
        rows = list(reader)
        self.assertEqual(rows[0][:4], ["rank", "invoice", "customer", "due_date"])
        self.assertEqual(len(rows), 1 + 12)  # 12 open invoices in the fixture
        self.assertEqual(rows[1][0], "1")

    def test_top_limits_rows(self) -> None:
        rows = list(csv.reader(io.StringIO(render_chase_csv(sample_report(), top=3))))
        self.assertEqual(len(rows), 4)


class HtmlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = render_html(sample_report(), top=5)

    def test_is_a_document(self) -> None:
        self.assertTrue(self.text.startswith("<!DOCTYPE html>"))
        self.assertIn("</html>", self.text)
        self.assertIn("Aging report — 2026-10-18", self.text)

    def test_contains_bars_and_table(self) -> None:
        self.assertIn("Aging buckets", self.text)
        self.assertIn("class='pill b90p'", self.text)
        self.assertIn("Chase list", self.text)

    def test_no_unescaped_selector_garbage(self) -> None:
        self.assertNotIn("pill\\", self.text)


def run_cli(*argv: str) -> tuple[int, str]:
    from agingradar.cli import main

    out = io.StringIO()
    err = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(list(argv))
    return code, out.getvalue() + err.getvalue()


class CliTests(unittest.TestCase):
    def test_report_markdown_stdout(self) -> None:
        code, out = run_cli("report", EXAMPLE_CSV, "--as-of", "2026-10-18")
        self.assertEqual(code, 0)
        self.assertIn("# Aging report — 2026-10-18", out)

    def test_report_html_to_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "report.html")
            code, out = run_cli("report", EXAMPLE_CSV, "--as-of", "2026-10-18",
                                "--format", "html", "-o", target)
            self.assertEqual(code, 0)
            self.assertIn("wrote", out)
            with open(target, encoding="utf-8") as fh:
                self.assertIn("<!DOCTYPE html>", fh.read())

    def test_report_csv_format(self) -> None:
        code, out = run_cli("report", EXAMPLE_CSV, "--as-of", "2026-10-18", "--format", "csv")
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("rank,invoice,customer"))

    def test_check_command(self) -> None:
        code, out = run_cli("check", EXAMPLE_CSV)
        self.assertEqual(code, 0)
        self.assertIn("OK", out)
        self.assertIn("16 invoices", out)

    def test_fail_overdue_ratio_gate(self) -> None:
        code, out = run_cli("report", EXAMPLE_CSV, "--as-of", "2026-10-18",
                            "--fail-overdue-ratio", "0.5")
        self.assertEqual(code, 1)
        self.assertIn("exceeds the gate", out)
        code, _ = run_cli("report", EXAMPLE_CSV, "--as-of", "2026-10-18",
                          "--fail-overdue-ratio", "0.999")
        self.assertEqual(code, 0)

    def test_missing_file_is_usage_error(self) -> None:
        code, out = run_cli("check", "/no/such/invoices.csv")
        self.assertEqual(code, 2)
        self.assertIn("error:", out)

    def test_bad_as_of_is_usage_error(self) -> None:
        code, out = run_cli("report", EXAMPLE_CSV, "--as-of", "someday")
        self.assertEqual(code, 2)

    def test_as_of_defaults_to_today(self) -> None:
        code, out = run_cli("check", EXAMPLE_CSV)
        self.assertEqual(code, 0)
        self.assertIn(str(date.today()), out)

    def test_demo_summary_is_valid_json(self) -> None:
        path = os.path.join(os.path.dirname(__file__), "..", "results", "demo-summary.json")
        if not os.path.exists(path):
            self.skipTest("demo has not been run")
        with open(path, encoding="utf-8") as fh:
            payload = json.load(fh)
        self.assertEqual(payload["as_of"], "2026-10-18")
        self.assertIn("top_chase", payload)
        self.assertEqual(payload["ignored"], 2)


class DeterminismTests(unittest.TestCase):
    def test_same_input_same_markdown(self) -> None:
        a = render_markdown(sample_report(), top=5)
        b = render_markdown(sample_report(), top=5)
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()