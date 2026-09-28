"""A tiny in-memory table keyed by string id."""

from __future__ import annotations

from typing import Callable, Generic, Iterator, TypeVar

from core.errors import NotFound, ValidationError

T = TypeVar("T")


class Registry(Generic[T]):
    def __init__(self, kind: str, key: Callable[[T], str]) -> None:
        self.kind = kind
        self._key = key
        self._rows: dict[str, T] = {}

    def add(self, row: T) -> T:
        key = self._key(row)
        if key in self._rows:
            raise ValidationError(f"{self.kind} already exists: {key}")
        self._rows[key] = row
        return row

    def get(self, key: str) -> T:
        try:
            return self._rows[key]
        except KeyError:
            raise NotFound(self.kind, key) from None

    def has(self, key: str) -> bool:
        return key in self._rows

    def all(self) -> list[T]:
        return list(self._rows.values())

    def __len__(self) -> int:
        return len(self._rows)

    def __iter__(self) -> Iterator[T]:
        return iter(self._rows.values())
