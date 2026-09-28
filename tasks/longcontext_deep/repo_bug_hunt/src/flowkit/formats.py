"""Human-readable rendering of statistics and tables for the nightly e-mail."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime

from flowkit.aggregate import Stats


def fmt_number(value: float, *, decimals: int = 2) -> str:
    if float(value).is_integer() and decimals == 0:
        return f"{int(value):,}"
    return f"{value:,.{decimals}f}"


def fmt_duration(seconds: float) -> str:
    seconds = int(round(seconds))
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}h{minutes:02d}m{secs:02d}s"
    if minutes:
        return f"{minutes}m{secs:02d}s"
    return f"{secs}s"


def stats_row(label: str, stats: Stats) -> list[str]:
    return [
        label,
        str(stats.count),
        fmt_number(stats.mean),
        fmt_number(stats.median),
        fmt_number(stats.p95),
        fmt_number(stats.maximum),
    ]


STATS_HEADER = ["group", "n", "mean", "median", "p95", "max"]


def render_table(rows: Iterable[list[str]], header: list[str] | None = None) -> str:
    rows = [list(r) for r in rows]
    columns = len(header) if header else (len(rows[0]) if rows else 0)
    widths = [0] * columns
    for row in ([header] if header else []) + rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))
    lines: list[str] = []
    if header:
        lines.append("  ".join(h.ljust(widths[i]) for i, h in enumerate(header)))
        lines.append("  ".join("-" * widths[i] for i in range(columns)))
    for row in rows:
        cells = []
        for i, cell in enumerate(row):
            cells.append(cell.rjust(widths[i]) if i > 0 else cell.ljust(widths[i]))
        lines.append("  ".join(cells))
    return "\n".join(lines)


def render_report(report: Mapping[datetime, Mapping[str, Stats]]) -> str:
    sections: list[str] = []
    for start in sorted(report):
        rows = [stats_row(group, stats) for group, stats in sorted(report[start].items())]
        sections.append(f"== window starting {start.isoformat()} ==")
        sections.append(render_table(rows, STATS_HEADER))
        sections.append("")
    return "\n".join(sections).rstrip() + "\n"
