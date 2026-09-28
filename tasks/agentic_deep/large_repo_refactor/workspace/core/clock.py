"""A deterministic clock: every call to ``now()`` advances by one tick."""

from __future__ import annotations


class Clock:
    def __init__(self, start: int = 1_700_000_000) -> None:
        self._now = start

    def now(self) -> int:
        self._now += 1
        return self._now

    def peek(self) -> int:
        return self._now
