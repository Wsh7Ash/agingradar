"""Renderers: markdown table report, chase CSV, standalone HTML page."""

from __future__ import annotations

import csv
import io
from datetime import date

from .aging import AgingReport, AgingRow, BUCKETS
from .model import format_money


def _money(row: AgingRow) -> str:
    return format_money(row.balance_cents, row.invoice.currency)


def render_markdown(report: AgingReport, top: int = 10) -> str:
    currency = _single_currency(report)
    lines: list[str] = []
    lines.append(f"# Aging report — {report.as_of.isoformat()}")
    lines.append("")
    lines.append(f"- invoices analyzed: **{len(report.rows)} open**"
                 f" (+ {len(report.paid_in_period)} paid, {len(report.ignored)} ignored)")
    lines.append(f"- outstanding: **{format_money(report.total_outstanding(), currency)}**")
    lines.append(f"- overdue: **{format_money(report.total_overdue(), currency)}**"
                 f" ({report.overdue_ratio():.0%} of outstanding)")
    if report.average_days_to_pay() is not None:
        lines.append(f"- average days to payment (paid invoices): **{report.average_days_to_pay():.1f}**")
    lines.append("")

    lines.append("## Aging buckets")
    lines.append("")
    lines.append("| Bucket | Invoices | Balance |")
    lines.append("|---|---|---|")
    totals = report.bucket_totals()
    counts = report.bucket_counts()
    for name, _, _ in BUCKETS:
        currency = _single_currency(report)
        lines.append(f"| {name} | {counts[name]} | {format_money(totals[name], currency)} |")
    lines.append("")

    lines.append("## Top customers by exposure")
    lines.append("")
    lines.append("| Customer | Outstanding | Overdue | Oldest overdue | Late payments |")
    lines.append("|---|---|---|---|---|")
    for customer, totals_c in sorted(
        report.customer_totals().items(), key=lambda kv: -kv[1]["total"]
    )[:10]:
        currency = _currency_for(report, customer)
        late = report.late_payers.get(customer, 0)
        flag = " ⚠" if late else ""
        lines.append(
            f"| {customer} | {format_money(totals_c['total'], currency)} | "
            f"{format_money(totals_c['overdue'], currency)} | {totals_c['oldest_days']}d | {late}{flag} |"
        )
    lines.append("")

    lines.append(f"## Chase list (top {min(top, len(report.chase_list()))})")
    lines.append("")
    lines.append("| # | Invoice | Customer | Due | Days | Bucket | Balance | Score |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for i, row in enumerate(report.chase_list(top), 1):
        days = f"+{row.days_overdue}" if row.days_overdue > 0 else str(row.days_overdue)
        lines.append(
            f"| {i} | {row.invoice.number} | {row.invoice.customer} | {row.invoice.due_date.isoformat()} | "
            f"{days} | {row.bucket} | {_money(row)} | {row.score_pct} |"
        )
    lines.append("")
    lines.append("_Scores combine amount, aging bucket and the customer's late-payment "
                 "history; 100 = highest-priority invoice in this run. Software "
                 "output, not financial advice._")
    return "\n".join(lines) + "\n"


def render_chase_csv(report: AgingReport, top: int | None = None) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        ["rank", "invoice", "customer", "due_date", "days_overdue", "bucket",
         "balance", "currency", "score_pct", "late_history"]
    )
    for i, row in enumerate(report.chase_list(top), 1):
        writer.writerow(
            [i, row.invoice.number, row.invoice.customer, row.invoice.due_date.isoformat(),
             row.days_overdue, row.bucket, f"{row.balance_cents / 100:.2f}",
             row.invoice.currency, row.score_pct, "yes" if row.late_history else "no"]
        )
    return buf.getvalue()


def render_html(report: AgingReport, top: int = 10) -> str:
    totals = report.bucket_totals()
    counts = report.bucket_counts()
    currency = _single_currency(report)
    max_bucket = max(totals.values(), default=1) or 1
    bars = []
    for name, _, _ in BUCKETS:
        pct = 100 * totals[name] / max_bucket
        bars.append(
            f'<div class="bar-row"><span class="bname">{name}</span>'
            f'<span class="bar"><span class="fill" style="width:{pct:.1f}%"></span></span>'
            f'<span class="bval">{format_money(totals[name], currency)}</span>'
            f'<span class="bcount">{counts[name]} inv.</span></div>'
        )
    rows = []
    safe_class = {"current": "bcur", "1-30": "b130", "31-60": "b3160", "61-90": "b6190", "90+": "b90p"}
    for i, row in enumerate(report.chase_list(top), 1):
        badge = "late" if row.late_history else ""
        cls = safe_class.get(row.bucket, "bcur")
        rows.append(
            f"<tr><td>{i}</td><td>{row.invoice.number}</td><td>{row.invoice.customer}</td>"
            f"<td>{row.invoice.due_date.isoformat()}</td><td>{row.days_overdue:+d}</td>"
            f"<td><span class='pill {cls}'>{row.bucket}</span></td>"
            f"<td class='num'>{_money(row)}</td><td class='num'>{row.score_pct}</td>"
            f"<td>{badge}</td></tr>"
        )
    late_customers = sorted(report.late_payers.items(), key=lambda kv: -kv[1])
    late_html = ", ".join(f"{c} ({n})" for c, n in late_customers) or "none in history"
    overdue_pct = f"{report.overdue_ratio():.0%}"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Aging report — {report.as_of.isoformat()}</title>
<style>
  :root {{ --ink:#1c2430; --muted:#66707d; --line:#e4e8ee; --bg:#f6f8fb; --warn:#b4472e; }}
  body {{ font:15px/1.5 system-ui, sans-serif; color:var(--ink); background:var(--bg); margin:0; }}
  main {{ max-width:980px; margin:0 auto; padding:32px 20px 64px; }}
  h1 {{ font-size:22px; margin:0 0 4px; }}
  .meta {{ color:var(--muted); margin-bottom:24px; }}
  .cards {{ display:flex; gap:12px; flex-wrap:wrap; margin-bottom:28px; }}
  .card {{ background:#fff; border:1px solid var(--line); border-radius:10px; padding:14px 18px; min-width:180px; }}
  .card b {{ display:block; font-size:20px; }}
  .card span {{ color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:.04em; }}
  section {{ background:#fff; border:1px solid var(--line); border-radius:10px; padding:18px 20px; margin-bottom:20px; }}
  .bar-row {{ display:grid; grid-template-columns:70px 1fr 130px 70px; gap:10px; align-items:center; margin:6px 0; }}
  .bar {{ background:#eef1f5; border-radius:6px; height:16px; overflow:hidden; }}
  .fill {{ display:block; height:100%; background:linear-gradient(90deg,#e0a15c,#b4472e); }}
  .bval {{ text-align:right; font-variant-numeric:tabular-nums; }}
  .bcount {{ color:var(--muted); font-size:12px; }}
  table {{ width:100%; border-collapse:collapse; }}
  th, td {{ text-align:left; padding:7px 8px; border-bottom:1px solid var(--line); }}
  th {{ font-size:12px; text-transform:uppercase; letter-spacing:.04em; color:var(--muted); }}
  td.num {{ text-align:right; font-variant-numeric:tabular-nums; }}
  .pill {{ padding:2px 8px; border-radius:999px; font-size:12px; background:#eef1f5; }}
  .b90p, .b6190 {{ background:#f7dcd4; color:var(--warn); }}
  .late {{ color:var(--warn); font-weight:600; }}
  footer {{ color:var(--muted); font-size:13px; }}
</style>
</head>
<body>
<main>
  <h1>Aging report — {report.as_of.isoformat()}</h1>
  <div class="meta">{len(report.rows)} open invoices · source: {report.source}</div>
  <div class="cards">
    <div class="card"><span>Outstanding</span><b>{format_money(report.total_outstanding(), currency)}</b></div>
    <div class="card"><span>Overdue</span><b>{format_money(report.total_overdue(), currency)}</b> {overdue_pct} of outstanding</div>
    <div class="card"><span>Late payers (history)</span><b>{len(report.late_payers)}</b></div>
  </div>
  <section><h2>Aging buckets</h2>{''.join(bars)}</section>
  <section><h2>Chase list — top {min(top, len(report.chase_list()))}</h2>
    <table>
      <tr><th>#</th><th>Invoice</th><th>Customer</th><th>Due</th><th>Days</th><th>Bucket</th><th>Balance</th><th>Score</th><th>History</th></tr>
      {''.join(rows)}
    </table>
  </section>
  <footer>Late-payment history: {late_html}. Scores combine amount, aging bucket and
  late-payment history; this page is generated software output, not financial advice.</footer>
</main>
</body>
</html>
"""


def _single_currency(report: AgingReport) -> str:
    currencies = {r.invoice.currency for r in report.open_rows} or {"USD"}
    return sorted(currencies)[0] if len(currencies) == 1 else "USD"


def _currency_for(report: AgingReport, customer: str) -> str:
    for row in report.open_rows:
        if row.invoice.customer == customer:
            return row.invoice.currency
    return "USD"