"""Tracks cache keys that must be dropped."""

from __future__ import annotations

from core.events import Event, EventType


class CacheInvalidatorPlugin:
    name = "cache_invalidator"

    def __init__(self, app) -> None:
        self.app = app
        self.invalidated: list[str] = []

    def register(self, app) -> None:
        app.bus.subscribe(EventType.CUSTOMER_UPGRADED, self._on_upgraded)
        app.bus.subscribe(EventType.ORDER_CREATED, self._on_order_created)
        app.bus.subscribe(EventType.ORDER_PAID, self._on_order_paid)
        app.bus.subscribe(EventType.ORDER_CANCELLED, self._on_order_cancelled)
        app.bus.subscribe(EventType.ORDER_SHIPPED, self._on_order_shipped)

    def _on_upgraded(self, event: Event) -> None:
        payload = event.payload
        self.invalidated.append(f"customer:{payload['customer_id']}")

    def _on_order_created(self, event: Event) -> None:
        payload = event.payload
        self.invalidated.append(f"orders:{payload['customer_id']}")

    def _on_order_paid(self, event: Event) -> None:
        payload = event.payload
        self.invalidated.append(f"order:{payload['order_id']}")

    def _on_order_cancelled(self, event: Event) -> None:
        payload = event.payload
        self.invalidated.append(f"order:{payload['order_id']}")

    def _on_order_shipped(self, event: Event) -> None:
        payload = event.payload
        self.invalidated.append(f"order:{payload['order_id']}")


def register(app):
    plugin = CacheInvalidatorPlugin(app)
    plugin.register(app)
    return plugin
