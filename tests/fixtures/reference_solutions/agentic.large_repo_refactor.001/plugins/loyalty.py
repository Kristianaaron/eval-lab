"""Loyalty points per customer."""

from __future__ import annotations

from core.events import Event, EventType


class LoyaltyPlugin:
    name = "loyalty"

    def __init__(self, app) -> None:
        self.app = app
        self.points: dict[str, int] = {}

    def register(self, app) -> None:
        app.bus.subscribe(EventType.ORDER_PAID, self._on_paid)
        app.bus.subscribe(EventType.PAYMENT_REFUNDED, self._on_refunded)
        app.bus.subscribe(EventType.CUSTOMER_UPGRADED, self._on_upgraded)

    def _on_paid(self, event: Event) -> None:
        payload = event.payload
        earned = payload["total_cents"] // 100 * self.app.settings.loyalty_points_per_dollar
        self.points[payload["customer_id"]] = self.points.get(payload["customer_id"], 0) + earned

    def _on_refunded(self, event: Event) -> None:
        payload = event.payload
        order = self.app.services.orders.get(payload["order_id"])
        lost = payload["amount_cents"] // 100 * self.app.settings.loyalty_points_per_dollar
        self.points[order.customer_id] = max(0, self.points.get(order.customer_id, 0) - lost)

    def _on_upgraded(self, event: Event) -> None:
        payload = event.payload
        if payload["tier"] == "gold":
            self.points[payload["customer_id"]] = self.points.get(payload["customer_id"], 0) + 100


def register(app):
    plugin = LoyaltyPlugin(app)
    plugin.register(app)
    return plugin
