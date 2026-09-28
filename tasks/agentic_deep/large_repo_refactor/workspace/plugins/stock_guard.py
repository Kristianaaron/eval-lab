"""Raises operational alerts when stock runs low."""

from __future__ import annotations

from core.events import on


class StockGuardPlugin:
    name = "stock_guard"

    def __init__(self, app) -> None:
        self.app = app
        self.alerts: list[tuple[str, int]] = []

    def register(self, app) -> None:
        on("inventory.low", self._on_low)
        on("inventory.released", self._on_released)

    def _on_low(self, payload: dict) -> None:
        self.alerts.append((payload["sku"], payload["remaining"]))
        self.app.services.notifications.send("ops", self.app.settings.ops_channel, f"Low stock: {payload['sku']} ({payload['remaining']} left)")

    def _on_released(self, payload: dict) -> None:
        for sku, _ in payload["lines"]:
            self.alerts = [(s, r) for s, r in self.alerts if s != sku]


def register(app):
    plugin = StockGuardPlugin(app)
    plugin.register(app)
    return plugin
