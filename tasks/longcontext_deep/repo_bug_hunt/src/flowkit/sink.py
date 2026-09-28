"""Sinks: where finished records go."""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from flowkit.records import Record


class Sink(Protocol):
    def write(self, records: Iterable[Record]) -> int: ...


def _encode(record: Record) -> dict[str, Any]:
    body: dict[str, Any] = dict(record.fields)
    body["_source"] = record.source
    if record.timestamp is not None:
        body["_ts"] = record.timestamp.isoformat().replace("+00:00", "Z")
    if record.tags:
        body["_tags"] = list(record.tags)
    return body


class MemorySink:
    def __init__(self) -> None:
        self.items: list[dict[str, Any]] = []

    def write(self, records: Iterable[Record]) -> int:
        before = len(self.items)
        self.items.extend(_encode(r) for r in records)
        return len(self.items) - before


class JsonlSink:
    def __init__(self, path: str | Path, *, append: bool = True) -> None:
        self.path = Path(path)
        self.append = append

    def write(self, records: Iterable[Record]) -> int:
        mode = "a" if self.append else "w"
        n = 0
        with self.path.open(mode, encoding="utf-8") as fh:
            for r in records:
                fh.write(json.dumps(_encode(r), sort_keys=True, default=_default) + "\n")
                n += 1
        return n


def _default(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)
