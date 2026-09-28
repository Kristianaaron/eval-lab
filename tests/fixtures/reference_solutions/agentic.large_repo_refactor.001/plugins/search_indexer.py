"""Keeps a searchable customer index up to date."""

from __future__ import annotations

from core.events import Event, EventType


class SearchIndexerPlugin:
    name = "search_indexer"

    def __init__(self, app) -> None:
        self.app = app
        self.index: dict[str, dict] = {}

    def register(self, app) -> None:
        app.bus.subscribe(EventType.CUSTOMER_REGISTERED, self._on_registered)
        app.bus.subscribe(EventType.CUSTOMER_UPGRADED, self._on_upgraded)

    def _on_registered(self, event: Event) -> None:
        payload = event.payload
        self.index[payload["customer_id"]] = {"name": payload["name"], "email": payload["email"], "tier": "standard"}

    def _on_upgraded(self, event: Event) -> None:
        payload = event.payload
        entry = self.index.setdefault(payload["customer_id"], {})
        entry["tier"] = payload["tier"]

    def search(self, text: str) -> list[str]:
        needle = text.lower()
        return sorted(cid for cid, doc in self.index.items() if needle in str(doc.get("name", "")).lower())


def register(app):
    plugin = SearchIndexerPlugin(app)
    plugin.register(app)
    return plugin
