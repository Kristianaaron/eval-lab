"""Numbers for the end-of-day report."""

from __future__ import annotations

import core.events as ev


class ReportingPlugin:
    name = "reporting"

    def __init__(self, app) -> None:
        self.app = app
        self.delivered: list[str] = []
        self.cancelled: list[tuple[str, str]] = []
        self.captured_cents = 0

    def register(self, app) -> None:
        ev.on("shipment.delivered", self._on_delivered)
        ev.on("order.cancelled", self._on_cancelled)
        ev.on("payment.captured", self._on_captured)

    def _on_delivered(self, payload: dict) -> None:
        self.delivered.append(payload["order_id"])

    def _on_cancelled(self, payload: dict) -> None:
        self.cancelled.append((payload["order_id"], payload["reason"]))

    def _on_captured(self, payload: dict) -> None:
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
