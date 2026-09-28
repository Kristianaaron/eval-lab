"""Mirrors reservations to the warehouse system."""

from __future__ import annotations

from core.events import Event, EventType


class WarehouseSyncPlugin:
    name = "warehouse_sync"

    def __init__(self, app) -> None:
        self.app = app
        self.pending: dict[str, list] = {}
        self.shipped: list[str] = []

    def register(self, app) -> None:
        app.bus.subscribe(EventType.INVENTORY_RESERVED, self._on_reserved)
        app.bus.subscribe(EventType.INVENTORY_RELEASED, self._on_released)
        app.bus.subscribe(EventType.SHIPMENT_DISPATCHED, self._on_dispatched)

    def _on_reserved(self, event: Event) -> None:
        payload = event.payload
        self.pending[payload["order_id"]] = list(payload["lines"])

    def _on_released(self, event: Event) -> None:
        payload = event.payload
        self.pending.pop(payload["order_id"], None)

    def _on_dispatched(self, event: Event) -> None:
        payload = event.payload
        self.pending.pop(payload["order_id"], None)
        self.shipped.append(payload["order_id"])


def register(app):
    plugin = WarehouseSyncPlugin(app)
    plugin.register(app)
    return plugin
