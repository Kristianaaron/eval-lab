"""Product analytics."""

from __future__ import annotations

from core import events
from core.constants import EVENT_CART_ITEM_ADDED, EVENT_CUSTOMER_REGISTERED, EVENT_ORDER_CREATED


class AnalyticsPlugin:
    name = "analytics"

    def __init__(self, app) -> None:
        self.app = app
        self.popular: dict[str, int] = {}
        self.signups = 0
        self.basket_sizes: list[int] = []

    def register(self, app) -> None:
        events.on(EVENT_CART_ITEM_ADDED, self._on_item_added)
        events.on(EVENT_CUSTOMER_REGISTERED, self._on_registered)
        events.on(EVENT_ORDER_CREATED, self._on_order_created)

    def _on_item_added(self, payload: dict) -> None:
        self.popular[payload["sku"]] = self.popular.get(payload["sku"], 0) + payload["quantity"]

    def _on_registered(self, payload: dict) -> None:
        self.signups += 1

    def _on_order_created(self, payload: dict) -> None:
        self.basket_sizes.append(len(payload["lines"]))

    def top_sku(self) -> str | None:
        if not self.popular:
            return None
        return max(sorted(self.popular), key=lambda sku: self.popular[sku])


def register(app):
    plugin = AnalyticsPlugin(app)
    plugin.register(app)
    return plugin
