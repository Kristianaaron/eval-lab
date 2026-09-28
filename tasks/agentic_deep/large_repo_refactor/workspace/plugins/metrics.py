"""Counters for the ops dashboard."""

from __future__ import annotations

from core.events import on


class MetricsPlugin:
    name = "metrics"

    def __init__(self, app) -> None:
        self.app = app
        self.counts: dict[str, int] = {}
        self.revenue_cents = 0

    def register(self, app) -> None:
        on("order.created", self._on_created)
        on("order.paid", self._on_paid)
        on("order.cancelled", self._on_cancelled)
        on("payment.failed", self._on_failed)
        on("shipment.delivered", self._on_delivered)

    def _on_created(self, payload: dict) -> None:
        self.counts["order.created"] = self.counts.get("order.created", 0) + 1

    def _on_paid(self, payload: dict) -> None:
        self.counts["order.paid"] = self.counts.get("order.paid", 0) + 1
        self.revenue_cents += payload["total_cents"]

    def _on_cancelled(self, payload: dict) -> None:
        self.counts["order.cancelled"] = self.counts.get("order.cancelled", 0) + 1

    def _on_failed(self, payload: dict) -> None:
        self.counts["payment.failed"] = self.counts.get("payment.failed", 0) + 1

    def _on_delivered(self, payload: dict) -> None:
        self.counts["shipment.delivered"] = self.counts.get("shipment.delivered", 0) + 1

    def snapshot(self) -> dict[str, int]:
        return dict(sorted(self.counts.items()))


def register(app):
    plugin = MetricsPlugin(app)
    plugin.register(app)
    return plugin
