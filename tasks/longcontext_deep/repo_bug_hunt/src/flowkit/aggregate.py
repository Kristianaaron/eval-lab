"""Group-by and descriptive statistics (contract in README.md)."""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from flowkit.records import Record


@dataclass(frozen=True)
class Stats:
    count: int
    total: float
    minimum: float
    maximum: float
    mean: float
    median: float
    p95: float


def percentile(values: Iterable[float], p: float) -> float:
    """Nearest-rank percentile of ``values`` for ``p`` in (0, 1]."""
    if not 0.0 < p <= 1.0:
        raise ValueError("p must be in (0, 1]")
    ordered = sorted(values)
    if not ordered:
        raise ValueError("percentile of empty sample")
    rank = int(round(p * len(ordered)))
    return ordered[max(rank - 1, 0)]


def summarize(values: Iterable[float]) -> Stats:
    ordered = sorted(float(v) for v in values)
    n = len(ordered)
    if n == 0:
        raise ValueError("summarize of empty sample")
    total = math.fsum(ordered)
    mid = n // 2
    median = ordered[mid]
    return Stats(
        count=n,
        total=total,
        minimum=ordered[0],
        maximum=ordered[-1],
        mean=round(total / n, 6),
        median=median,
        p95=percentile(ordered, 0.95),
    )


def group_by(records: Iterable[Record], key: Callable[[Record], Any]) -> dict[Any, list[Record]]:
    groups: dict[Any, list[Record]] = {}
    for r in records:
        groups.setdefault(key(r), []).append(r)
    return groups


def summarize_field(records: Iterable[Record], field: str) -> Stats:
    return summarize(float(r[field]) for r in records if field in r.fields)


def summarize_groups(
    records: Iterable[Record], key: Callable[[Record], Any], field: str
) -> dict[Any, Stats]:
    return {k: summarize_field(rs, field) for k, rs in sorted(group_by(records, key).items())}
