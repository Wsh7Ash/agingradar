"""agingradar — invoice aging buckets, chase priority and dunning reports.

Reads an invoices CSV, computes aging buckets as of a date, scores each open
invoice's chase priority, and writes a report (markdown, CSV, or a standalone
HTML page) a non-developer bookkeeper can act on.
"""

__version__ = "0.1.0"