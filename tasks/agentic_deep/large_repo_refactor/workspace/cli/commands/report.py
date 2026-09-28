"""``shop report``: plugin summaries."""

from __future__ import annotations

from typing import TextIO


def show_report(app, out: TextIO) -> None:
    metrics = app.plugins["metrics"]
    reporting = app.plugins["reporting"]
    out.write(reporting.summary() + "\n")
    for name, count in metrics.snapshot().items():
        out.write(f"{name}: {count}\n")
    out.write(f"revenue_cents={metrics.revenue_cents}\n")
