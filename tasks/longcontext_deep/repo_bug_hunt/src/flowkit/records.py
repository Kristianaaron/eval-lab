"""The Record type: an immutable mapping with a timestamp and a source tag."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from flowkit.errors import SchemaError


@dataclass(frozen=True)
class Record(Mapping[str, Any]):
    fields: Mapping[str, Any]
    timestamp: datetime | None = None
    source: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)

    def __getitem__(self, key: str) -> Any:
        return self.fields[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self.fields)

    def __len__(self) -> int:
        return len(self.fields)

    def with_fields(self, **changes: Any) -> Record:
        merged = dict(self.fields)
        merged.update(changes)
        return Record(merged, self.timestamp, self.source, self.tags)

    def without(self, *keys: str) -> Record:
        return Record(
            {k: v for k, v in self.fields.items() if k not in keys},
            self.timestamp,
            self.source,
            self.tags,
        )

    def tagged(self, *tags: str) -> Record:
        return Record(self.fields, self.timestamp, self.source, tuple(dict.fromkeys(self.tags + tags)))


def parse_timestamp(value: str) -> datetime:
    """Parse ISO-8601; a trailing ``Z`` means UTC, naive values are assumed UTC."""
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise SchemaError(f"bad timestamp: {value!r}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def key_of(record: Record, *names: str, separator: str = "|") -> str:
    """Build a composite key from the named fields; missing fields raise."""
    parts: list[str] = []
    for name in names:
        if name not in record.fields:
            raise SchemaError(f"record lacks key field {name!r}")
        parts.append(str(record.fields[name]))
    return separator.join(parts)
