"""Tumbling and sliding time windows over timestamped records.

Windows are half-open ``[start, end)``. Records without a timestamp are
rejected with ``SchemaError``. Input need not be sorted; output windows are
sorted by start time and each window's records keep their input order.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from flowkit.errors import SchemaError
from flowkit.records import Record


@dataclass
class Window:
    start: datetime
    end: datetime
    records: list[Record] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.records)


def _ts(record: Record) -> datetime:
    if record.timestamp is None:
        raise SchemaError("record has no timestamp")
    return record.timestamp


def _floor(ts: datetime, size: timedelta, origin: datetime) -> datetime:
    offset = (ts - origin) // size
    return origin + offset * size


def tumbling(records: Iterable[Record], size: timedelta, origin: datetime) -> list[Window]:
    if size <= timedelta(0):
        raise ValueError("window size must be positive")
    buckets: dict[datetime, Window] = {}
    for r in records:
        start = _floor(_ts(r), size, origin)
        buckets.setdefault(start, Window(start, start + size)).records.append(r)
    return [buckets[k] for k in sorted(buckets)]


def sliding(
    records: Iterable[Record], size: timedelta, step: timedelta, origin: datetime
) -> list[Window]:
    """Overlapping windows of ``size`` starting every ``step`` from ``origin``."""
    if size <= timedelta(0) or step <= timedelta(0):
        raise ValueError("window size and step must be positive")
    if step > size:
        raise ValueError("step must not exceed size")
    items = [(r, _ts(r)) for r in records]
    if not items:
        return []
    first = min(ts for _, ts in items)
    last = max(ts for _, ts in items)
    start = _floor(first, step, origin) - size + step
    windows: list[Window] = []
    while start <= last:
        end = start + size
        members = [r for r, ts in items if start <= ts < end]
        if members:
            windows.append(Window(start, end, members))
        start += step
    return windows
