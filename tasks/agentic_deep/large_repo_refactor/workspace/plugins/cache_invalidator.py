"""Tracks cache keys that must be dropped."""

from __future__ import annotations

from core import events


class CacheInvalidatorPlugin:
    name = "cache_invalidator"

    def __init__(self, app) -> None:
        self.app = app
        self.invalidated: list[str] = []

    def register(self, app) -> None:
        events.on("customer.upgraded", self._on_upgraded)
        events.on("order.created", self._on_order_created)
        events.on("order.paid", self._on_order_paid)
        events.on("order.cancelled", self._on_order_cancelled)
        events.on("order.shipped", self._on_order_shipped)

    def _on_upgraded(self, payload: dict) -> None:
        self.invalidated.append(f"customer:{payload['customer_id']}")

    def _on_order_created(self, payload: dict) -> None:
        self.invalidated.append(f"orders:{payload['customer_id']}")

    def _on_order_paid(self, payload: dict) -> None:
        self.invalidated.append(f"order:{payload['order_id']}")

    def _on_order_cancelled(self, payload: dict) -> None:
        self.invalidated.append(f"order:{payload['order_id']}")

    def _on_order_shipped(self, payload: dict) -> None:
        self.invalidated.append(f"order:{payload['order_id']}")


def register(app):
    plugin = CacheInvalidatorPlugin(app)
    plugin.register(app)
    return plugin
