"""Customer-facing e-mails."""

from __future__ import annotations

from core.events import Event, EventType


class EmailNotifierPlugin:
    name = "email_notifier"

    def __init__(self, app) -> None:
        self.app = app
        self.sent = 0

    def register(self, app) -> None:
        app.bus.subscribe(EventType.ORDER_CREATED, self._on_order_created)
        app.bus.subscribe(EventType.SHIPMENT_DISPATCHED, self._on_dispatched)
        app.bus.subscribe(EventType.PAYMENT_REFUNDED, self._on_refunded)

    def _on_order_created(self, event: Event) -> None:
        payload = event.payload
        customer = self.app.services.customers.get(payload["customer_id"])
        self.app.services.notifications.send("email", customer.email, f"Order {payload['order_id']} received")
        self.sent += 1

    def _on_dispatched(self, event: Event) -> None:
        payload = event.payload
        order = self.app.services.orders.get(payload["order_id"])
        customer = self.app.services.customers.get(order.customer_id)
        self.app.services.notifications.send("email", customer.email, f"Order {order.id} shipped via {payload['carrier']}")
        self.sent += 1

    def _on_refunded(self, event: Event) -> None:
        payload = event.payload
        order = self.app.services.orders.get(payload["order_id"])
        customer = self.app.services.customers.get(order.customer_id)
        self.app.services.notifications.send("email", customer.email, f"Refund of {payload['amount_cents']} cents for {order.id}")
        self.sent += 1


def register(app):
    plugin = EmailNotifierPlugin(app)
    plugin.register(app)
    return plugin
