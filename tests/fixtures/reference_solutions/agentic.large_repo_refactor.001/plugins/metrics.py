"""Counters for the ops dashboard."""

from __future__ import annotations

from core.events import Event, EventType


class MetricsPlugin:
    name = "metrics"

    def __init__(self, app) -> None:
        self.app = app
        self.counts: dict[str, int] = {}
        self.revenue_cents = 0

    def register(self, app) -> None:
        app.bus.subscribe(EventType.ORDER_CREATED, self._on_created)
        app.bus.subscribe(EventType.ORDER_PAID, self._on_paid)
        app.bus.subscribe(EventType.ORDER_CANCELLED, self._on_cancelled)
        app.bus.subscribe(EventType.PAYMENT_FAILED, self._on_failed)
        app.bus.subscribe(EventType.SHIPMENT_DELIVERED, self._on_delivered)

    def _on_created(self, event: Event) -> None:
        payload = event.payload
        self.counts["order.created"] = self.counts.get("order.created", 0) + 1

    def _on_paid(self, event: Event) -> None:
        payload = event.payload
        self.counts["order.paid"] = self.counts.get("order.paid", 0) + 1
        self.revenue_cents += payload["total_cents"]

    def _on_cancelled(self, event: Event) -> None:
        payload = event.payload
        self.counts["order.cancelled"] = self.counts.get("order.cancelled", 0) + 1

    def _on_failed(self, event: Event) -> None:
        payload = event.payload
        self.counts["payment.failed"] = self.counts.get("payment.failed", 0) + 1

    def _on_delivered(self, event: Event) -> None:
        payload = event.payload
        self.counts["shipment.delivered"] = self.counts.get("shipment.delivered", 0) + 1

    def snapshot(self) -> dict[str, int]:
        return dict(sorted(self.counts.items()))


def register(app):
    plugin = MetricsPlugin(app)
    plugin.register(app)
    return plugin
