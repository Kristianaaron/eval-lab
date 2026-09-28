"""Numbers for the end-of-day report."""

from __future__ import annotations

from core.events import Event, EventType


class ReportingPlugin:
    name = "reporting"

    def __init__(self, app) -> None:
        self.app = app
        self.delivered: list[str] = []
        self.cancelled: list[tuple[str, str]] = []
        self.captured_cents = 0

    def register(self, app) -> None:
        app.bus.subscribe(EventType.SHIPMENT_DELIVERED, self._on_delivered)
        app.bus.subscribe(EventType.ORDER_CANCELLED, self._on_cancelled)
        app.bus.subscribe(EventType.PAYMENT_CAPTURED, self._on_captured)

    def _on_delivered(self, event: Event) -> None:
        payload = event.payload
        self.delivered.append(payload["order_id"])

    def _on_cancelled(self, event: Event) -> None:
        payload = event.payload
        self.cancelled.append((payload["order_id"], payload["reason"]))

    def _on_captured(self, event: Event) -> None:
        payload = event.payload
        self.captured_cents += payload["amount_cents"]

    def summary(self) -> str:
        return (
            f"delivered={len(self.delivered)} cancelled={len(self.cancelled)} "
            f"captured_cents={self.captured_cents}"
        )


def register(app):
    plugin = ReportingPlugin(app)
    plugin.register(app)
    return plugin
