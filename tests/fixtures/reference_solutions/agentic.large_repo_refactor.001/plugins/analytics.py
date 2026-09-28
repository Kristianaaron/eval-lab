"""Product analytics."""

from __future__ import annotations

from core.events import Event, EventType


class AnalyticsPlugin:
    name = "analytics"

    def __init__(self, app) -> None:
        self.app = app
        self.popular: dict[str, int] = {}
        self.signups = 0
        self.basket_sizes: list[int] = []

    def register(self, app) -> None:
        app.bus.subscribe(EventType.CART_ITEM_ADDED, self._on_item_added)
        app.bus.subscribe(EventType.CUSTOMER_REGISTERED, self._on_registered)
        app.bus.subscribe(EventType.ORDER_CREATED, self._on_order_created)

    def _on_item_added(self, event: Event) -> None:
        payload = event.payload
        self.popular[payload["sku"]] = self.popular.get(payload["sku"], 0) + payload["quantity"]

    def _on_registered(self, event: Event) -> None:
        payload = event.payload
        self.signups += 1

    def _on_order_created(self, event: Event) -> None:
        payload = event.payload
        self.basket_sizes.append(len(payload["lines"]))

    def top_sku(self) -> str | None:
        if not self.popular:
            return None
        return max(sorted(self.popular), key=lambda sku: self.popular[sku])


def register(app):
    plugin = AnalyticsPlugin(app)
    plugin.register(app)
    return plugin
