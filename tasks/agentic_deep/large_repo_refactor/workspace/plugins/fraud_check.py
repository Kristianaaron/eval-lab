"""Cancels suspiciously large orders for manual review."""

from __future__ import annotations

import core.events as ev


class FraudCheckPlugin:
    name = "fraud_check"

    def __init__(self, app) -> None:
        self.app = app
        self.flagged: list[str] = []

    def register(self, app) -> None:
        ev.on("order.created", self._on_order_created)

    def _on_order_created(self, payload: dict) -> None:
        if payload["total_cents"] > self.app.settings.fraud_limit_cents:
            self.flagged.append(payload["order_id"])
            self.app.services.orders.cancel(payload["order_id"], "fraud review")


def register(app):
    plugin = FraudCheckPlugin(app)
    plugin.register(app)
    return plugin
