"""Customer-facing e-mails."""

from __future__ import annotations

from core import events


class EmailNotifierPlugin:
    name = "email_notifier"

    def __init__(self, app) -> None:
        self.app = app
        self.sent = 0

    def register(self, app) -> None:
        events.on("order.created", self._on_order_created)
        events.on("shipment.dispatched", self._on_dispatched)
        events.on("payment.refunded", self._on_refunded)

    def _on_order_created(self, payload: dict) -> None:
        customer = self.app.services.customers.get(payload["customer_id"])
        self.app.services.notifications.send("email", customer.email, f"Order {payload['order_id']} received")
        self.sent += 1

    def _on_dispatched(self, payload: dict) -> None:
        order = self.app.services.orders.get(payload["order_id"])
        customer = self.app.services.customers.get(order.customer_id)
        self.app.services.notifications.send("email", customer.email, f"Order {order.id} shipped via {payload['carrier']}")
        self.sent += 1

    def _on_refunded(self, payload: dict) -> None:
        order = self.app.services.orders.get(payload["order_id"])
        customer = self.app.services.customers.get(order.customer_id)
        self.app.services.notifications.send("email", customer.email, f"Refund of {payload['amount_cents']} cents for {order.id}")
        self.sent += 1


def register(app):
    plugin = EmailNotifierPlugin(app)
    plugin.register(app)
    return plugin
