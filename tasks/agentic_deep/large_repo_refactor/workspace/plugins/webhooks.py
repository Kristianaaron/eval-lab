"""Outbound webhooks (recorded, not sent)."""

from __future__ import annotations

from core import events


class WebhooksPlugin:
    name = "webhooks"

    def __init__(self, app) -> None:
        self.app = app
        self.deliveries: list[tuple[str, str, dict]] = []

    def register(self, app) -> None:
        events.on("order.paid", self._on_paid)
        events.on("shipment.dispatched", self._on_dispatched)
        events.on("order.cancelled", self._on_cancelled)

    def _on_paid(self, payload: dict) -> None:
        self.deliveries.append((self.app.settings.webhook_url, "order.paid", dict(payload)))

    def _on_dispatched(self, payload: dict) -> None:
        self.deliveries.append((self.app.settings.webhook_url, "shipment.dispatched", dict(payload)))

    def _on_cancelled(self, payload: dict) -> None:
        self.deliveries.append((self.app.settings.webhook_url, "order.cancelled", dict(payload)))


def register(app):
    plugin = WebhooksPlugin(app)
    plugin.register(app)
    return plugin
