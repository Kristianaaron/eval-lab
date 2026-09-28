"""Slack alerts for the on-call channel (recorded, not sent)."""

from __future__ import annotations

from core import events
from core.constants import EVENT_INVENTORY_LOW, EVENT_ORDER_CANCELLED, EVENT_PAYMENT_FAILED


class SlackAlertsPlugin:
    name = "slack_alerts"

    def __init__(self, app) -> None:
        self.app = app
        self.alerts: list[str] = []

    def register(self, app) -> None:
        events.on(EVENT_PAYMENT_FAILED, self._on_payment_failed)
        events.on(EVENT_INVENTORY_LOW, self._on_low)
        events.on(EVENT_ORDER_CANCELLED, self._on_cancelled)

    def _on_payment_failed(self, payload: dict) -> None:
        self.alerts.append(f"payment failed for {payload['order_id']}: {payload['reason']}")

    def _on_low(self, payload: dict) -> None:
        self.alerts.append(f"low stock {payload['sku']}={payload['remaining']}")

    def _on_cancelled(self, payload: dict) -> None:
        if payload["reason"] == "fraud review":
            self.alerts.append(f"fraud hold on {payload['order_id']}")


def register(app):
    plugin = SlackAlertsPlugin(app)
    plugin.register(app)
    return plugin
