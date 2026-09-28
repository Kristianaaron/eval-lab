"""Slack alerts for the on-call channel (recorded, not sent)."""

from __future__ import annotations

from core.events import Event, EventType


class SlackAlertsPlugin:
    name = "slack_alerts"

    def __init__(self, app) -> None:
        self.app = app
        self.alerts: list[str] = []

    def register(self, app) -> None:
        app.bus.subscribe(EventType.PAYMENT_FAILED, self._on_payment_failed)
        app.bus.subscribe(EventType.INVENTORY_LOW, self._on_low)
        app.bus.subscribe(EventType.ORDER_CANCELLED, self._on_cancelled)

    def _on_payment_failed(self, event: Event) -> None:
        payload = event.payload
        self.alerts.append(f"payment failed for {payload['order_id']}: {payload['reason']}")

    def _on_low(self, event: Event) -> None:
        payload = event.payload
        self.alerts.append(f"low stock {payload['sku']}={payload['remaining']}")

    def _on_cancelled(self, event: Event) -> None:
        payload = event.payload
        if payload["reason"] == "fraud review":
            self.alerts.append(f"fraud hold on {payload['order_id']}")


def register(app):
    plugin = SlackAlertsPlugin(app)
    plugin.register(app)
    return plugin
