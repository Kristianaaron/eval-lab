"""Loyalty points per customer."""

from __future__ import annotations

from core import events


class LoyaltyPlugin:
    name = "loyalty"

    def __init__(self, app) -> None:
        self.app = app
        self.points: dict[str, int] = {}

    def register(self, app) -> None:
        events.on("order.paid", self._on_paid)
        events.on("payment.refunded", self._on_refunded)
        events.on("customer.upgraded", self._on_upgraded)

    def _on_paid(self, payload: dict) -> None:
        earned = payload["total_cents"] // 100 * self.app.settings.loyalty_points_per_dollar
        self.points[payload["customer_id"]] = self.points.get(payload["customer_id"], 0) + earned

    def _on_refunded(self, payload: dict) -> None:
        order = self.app.services.orders.get(payload["order_id"])
        lost = payload["amount_cents"] // 100 * self.app.settings.loyalty_points_per_dollar
        self.points[order.customer_id] = max(0, self.points.get(order.customer_id, 0) - lost)

    def _on_upgraded(self, payload: dict) -> None:
        if payload["tier"] == "gold":
            self.points[payload["customer_id"]] = self.points.get(payload["customer_id"], 0) + 100


def register(app):
    plugin = LoyaltyPlugin(app)
    plugin.register(app)
    return plugin
