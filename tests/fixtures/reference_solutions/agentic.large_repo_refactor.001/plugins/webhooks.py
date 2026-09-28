"""Outbound webhooks (recorded, not sent)."""

from __future__ import annotations

from core.events import Event, EventType


class WebhooksPlugin:
    name = "webhooks"

    def __init__(self, app) -> None:
        self.app = app
        self.deliveries: list[tuple[str, str, dict]] = []

    def register(self, app) -> None:
        app.bus.subscribe(EventType.ORDER_PAID, self._on_paid)
        app.bus.subscribe(EventType.SHIPMENT_DISPATCHED, self._on_dispatched)
        app.bus.subscribe(EventType.ORDER_CANCELLED, self._on_cancelled)

    def _on_paid(self, event: Event) -> None:
        payload = event.payload
        self.deliveries.append((self.app.settings.webhook_url, "order.paid", dict(payload)))

    def _on_dispatched(self, event: Event) -> None:
        payload = event.payload
        self.deliveries.append((self.app.settings.webhook_url, "shipment.dispatched", dict(payload)))

    def _on_cancelled(self, event: Event) -> None:
        payload = event.payload
        self.deliveries.append((self.app.settings.webhook_url, "order.cancelled", dict(payload)))


def register(app):
    plugin = WebhooksPlugin(app)
    plugin.register(app)
    return plugin
