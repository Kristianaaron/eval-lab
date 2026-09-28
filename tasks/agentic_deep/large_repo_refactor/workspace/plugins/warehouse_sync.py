"""Mirrors reservations to the warehouse system."""

from __future__ import annotations

import core.events as ev


class WarehouseSyncPlugin:
    name = "warehouse_sync"

    def __init__(self, app) -> None:
        self.app = app
        self.pending: dict[str, list] = {}
        self.shipped: list[str] = []

    def register(self, app) -> None:
        ev.on("inventory.reserved", self._on_reserved)
        ev.on("inventory.released", self._on_released)
        ev.on("shipment.dispatched", self._on_dispatched)

    def _on_reserved(self, payload: dict) -> None:
        self.pending[payload["order_id"]] = list(payload["lines"])

    def _on_released(self, payload: dict) -> None:
        self.pending.pop(payload["order_id"], None)

    def _on_dispatched(self, payload: dict) -> None:
        self.pending.pop(payload["order_id"], None)
        self.shipped.append(payload["order_id"])


def register(app):
    plugin = WarehouseSyncPlugin(app)
    plugin.register(app)
    return plugin
