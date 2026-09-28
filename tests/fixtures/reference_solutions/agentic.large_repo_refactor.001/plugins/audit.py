"""Audit log: records every event that goes through the application."""

from __future__ import annotations

from core.events import Event, EventType


class AuditPlugin:
    name = "audit"

    def __init__(self) -> None:
        self.entries: list[tuple[str, dict]] = []

    def register(self, app) -> None:
        for event_type in EventType:
            app.bus.subscribe(event_type, self._record)

    def _record(self, event: Event) -> None:
        self.entries.append((event.type.value, dict(event.payload)))

    def names(self) -> list[str]:
        return [name for name, _ in self.entries]

    def count(self, name: str) -> int:
        return sum(1 for entry_name, _ in self.entries if entry_name == name)


def register(app):
    plugin = AuditPlugin()
    plugin.register(app)
    return plugin
