"""Short text messages for time-sensitive updates."""

from __future__ import annotations

from core.events import Event, EventType


class SmsNotifierPlugin:
    name = "sms_notifier"

    def __init__(self, app) -> None:
        self.app = app
        self.sent = 0

    def register(self, app) -> None:
        app.bus.subscribe(EventType.SHIPMENT_DELIVERED, self._on_delivered)
        app.bus.subscribe(EventType.PAYMENT_FAILED, self._on_payment_failed)

    def _on_delivered(self, event: Event) -> None:
        payload = event.payload
        order = self.app.services.orders.get(payload["order_id"])
        customer = self.app.services.customers.get(order.customer_id)
        self.app.services.notifications.send("sms", customer.email, f"Delivered: {order.id}")
        self.sent += 1

    def _on_payment_failed(self, event: Event) -> None:
        payload = event.payload
        order = self.app.services.orders.get(payload["order_id"])
        customer = self.app.services.customers.get(order.customer_id)
        self.app.services.notifications.send("sms", customer.email, f"Payment for {order.id} failed: {payload['reason']}")
        self.sent += 1


def register(app):
    plugin = SmsNotifierPlugin(app)
    plugin.register(app)
    return plugin
