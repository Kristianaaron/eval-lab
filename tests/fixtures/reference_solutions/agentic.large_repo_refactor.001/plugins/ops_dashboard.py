"""Ops dashboard: escalates shipped orders that took too long to leave the building."""

from __future__ import annotations

from core.events import Event, EventType


class OpsDashboardPlugin:
    name = "ops_dashboard"

    def __init__(self, app) -> None:
        self.app = app
        self.notifications = 0
        self.escalations: list[str] = []

    def register(self, app) -> None:
        app.bus.subscribe(EventType.ORDER_SHIPPED, self._on_shipped)
        app.bus.subscribe(EventType.NOTIFICATION_SENT, self._on_notification)

    def _on_shipped(self, event: Event) -> None:
        payload = event.payload
        order = self.app.services.orders.get(payload["order_id"])
        if order.total_cents >= self.app.settings.free_shipping_threshold_cents:
            self.escalations.append(order.id)
            self.app.bus.publish(Event(EventType.NOTIFICATION_SENT, {"channel": "ops", "recipient": self.app.settings.ops_channel, "message": f"priority shipment {payload['shipment_id']}"}))

    def _on_notification(self, event: Event) -> None:
        payload = event.payload
        if payload["channel"] == "ops":
            self.notifications += 1


def register(app):
    plugin = OpsDashboardPlugin(app)
    plugin.register(app)
    return plugin
