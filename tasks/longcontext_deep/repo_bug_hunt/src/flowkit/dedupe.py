"""De-duplicate records by key, keeping the latest by timestamp (ties: last seen)."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import datetime

from flowkit.records import Record


def keep_latest(records: Iterable[Record], key: Callable[[Record], str]) -> list[Record]:
    latest: dict[str, tuple[datetime | None, int, Record]] = {}
    for seq, r in enumerate(records):
        k = key(r)
        current = latest.get(k)
        if current is None:
            latest[k] = (r.timestamp, seq, r)
            continue
        ts_cur, _, _ = current
        if r.timestamp is None or ts_cur is None or r.timestamp >= ts_cur:
            latest[k] = (r.timestamp, seq, r)
    return [entry[2] for entry in sorted(latest.values(), key=lambda e: e[1])]


def duplicates(records: Iterable[Record], key: Callable[[Record], str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for r in records:
        counts[key(r)] = counts.get(key(r), 0) + 1
    return {k: c for k, c in counts.items() if c > 1}
