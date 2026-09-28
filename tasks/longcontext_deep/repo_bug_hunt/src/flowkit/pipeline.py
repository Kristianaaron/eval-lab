"""Stage composition and the nightly report entry point."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from datetime import datetime, timedelta

from flowkit.aggregate import Stats, summarize_groups
from flowkit.config import Config
from flowkit.dedupe import keep_latest
from flowkit.records import Record, key_of
from flowkit.sink import Sink
from flowkit.transforms import Transform, apply_all
from flowkit.windowing import tumbling

Stage = Callable[[Iterable[Record]], Iterable[Record]]


class Pipeline:
    def __init__(self) -> None:
        self._stages: list[Stage] = []

    def map(self, transform: Transform) -> Pipeline:
        self._stages.append(lambda rs, t=transform: apply_all(rs, t))
        return self

    def filter(self, predicate: Callable[[Record], bool]) -> Pipeline:
        self._stages.append(lambda rs, p=predicate: (r for r in rs if p(r)))
        return self

    def dedupe(self, *key_fields: str) -> Pipeline:
        self._stages.append(lambda rs, k=key_fields: keep_latest(rs, lambda r: key_of(r, *k)))
        return self

    def run(self, records: Iterable[Record]) -> Iterator[Record]:
        stream: Iterable[Record] = records
        for stage in self._stages:
            stream = stage(stream)
        yield from stream

    def run_to(self, records: Iterable[Record], sink: Sink) -> int:
        return sink.write(self.run(records))


def nightly_report(
    records: Iterable[Record],
    config: Config,
    *,
    field: str = "latency_ms",
    group_field: str = "service",
) -> dict[datetime, dict[str, Stats]]:
    """Per-window, per-service latency statistics for the nightly summary."""
    size = timedelta(minutes=config.getint("report", "window_minutes", 15) or 15)
    origin = datetime.fromisoformat(config.require("report", "origin"))
    out: dict[datetime, dict[str, Stats]] = {}
    for window in tumbling(records, size, origin):
        out[window.start] = summarize_groups(window.records, lambda r: r[group_field], field)
    return out
