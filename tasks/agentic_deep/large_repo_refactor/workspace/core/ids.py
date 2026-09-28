"""Sequential, human-readable identifiers such as ``ord-0001``."""

from __future__ import annotations


class IdGenerator:
    def __init__(self, prefix: str, width: int = 4) -> None:
        self.prefix = prefix
        self.width = width
        self._counter = 0

    def next(self) -> str:
        self._counter += 1
        return f"{self.prefix}-{self._counter:0{self.width}d}"

    @property
    def issued(self) -> int:
        return self._counter
