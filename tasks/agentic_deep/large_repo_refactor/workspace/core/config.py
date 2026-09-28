"""Runtime settings with sensible defaults for tests and the demo."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    low_stock_threshold: int = 3
    loyalty_points_per_dollar: int = 1
    gold_discount_percent: int = 10
    fraud_limit_cents: int = 50000
    free_shipping_threshold_cents: int = 7500
    webhook_url: str = "https://hooks.example.test/orders"
    ops_channel: str = "#ops"


DEFAULT_SETTINGS = Settings()
