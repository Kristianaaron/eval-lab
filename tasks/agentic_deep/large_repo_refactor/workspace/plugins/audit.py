"""Audit log: records every event that goes through the application."""

from __future__ import annotations

import core.events as ev
from core.constants import ALL_EVENTS


class AuditPlugin:
    name = "audit"

    def __init__(self) -> None:
        self.entries: list[tuple[str, dict]] = []

    def register(self, app) -> None:
        for name in ALL_EVENTS:
            ev.on(name, self._recorder(name))

    def _recorder(self, name: str):
        def record(payload: dict) -> None:
            self.entries.append((name, dict(payload)))

        return record

    def names(self) -> list[str]:
        return [name for name, _ in self.entries]

    def count(self, name: str) -> int:
        return sum(1 for entry_name, _ in self.entries if entry_name == name)


def register(app):
    plugin = AuditPlugin()
    plugin.register(app)
    return plugin
