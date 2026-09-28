"""Pure per-record transformations; every function returns a new Record."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from decimal import Decimal, InvalidOperation
from typing import Any

from flowkit.errors import SchemaError
from flowkit.records import Record

Transform = Callable[[Record], Record]


def rename(mapping: dict[str, str]) -> Transform:
    def apply(record: Record) -> Record:
        fields = {mapping.get(k, k): v for k, v in record.fields.items()}
        return Record(fields, record.timestamp, record.source, record.tags)

    return apply


def coerce(**types: str) -> Transform:
    """Coerce named fields to ``int``, ``float``, ``decimal`` or ``bool``."""

    def convert(kind: str, value: Any) -> Any:
        try:
            if kind == "int":
                return int(str(value).strip())
            if kind == "float":
                return float(str(value).strip())
            if kind == "decimal":
                return Decimal(str(value).strip())
            if kind == "bool":
                text = str(value).strip().lower()
                if text in ("1", "true", "yes"):
                    return True
                if text in ("0", "false", "no"):
                    return False
                raise ValueError(text)
        except (ValueError, InvalidOperation) as exc:
            raise SchemaError(f"cannot coerce {value!r} to {kind}") from exc
        raise SchemaError(f"unknown type {kind!r}")

    def apply(record: Record) -> Record:
        changes = {k: convert(t, record[k]) for k, t in types.items() if k in record.fields}
        return record.with_fields(**changes)

    return apply


def select(*names: str) -> Transform:
    def apply(record: Record) -> Record:
        missing = [n for n in names if n not in record.fields]
        if missing:
            raise SchemaError(f"missing fields: {', '.join(missing)}")
        return Record({n: record[n] for n in names}, record.timestamp, record.source, record.tags)

    return apply


def where(predicate: Callable[[Record], bool]) -> Callable[[Iterable[Record]], Iterator[Record]]:
    def apply(records: Iterable[Record]) -> Iterator[Record]:
        return (r for r in records if predicate(r))

    return apply


def chain(*transforms: Transform) -> Transform:
    def apply(record: Record) -> Record:
        for t in transforms:
            record = t(record)
        return record

    return apply


def apply_all(records: Iterable[Record], transform: Transform) -> Iterator[Record]:
    for r in records:
        yield transform(r)
