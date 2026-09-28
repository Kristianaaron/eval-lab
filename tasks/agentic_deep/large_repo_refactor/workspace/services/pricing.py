"""Order totals, including tier discounts."""

from __future__ import annotations

from core.config import Settings
from core.models import OrderLine


class PricingService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def subtotal(self, lines: tuple[OrderLine, ...]) -> int:
        return sum(line.total_cents for line in lines)

    def total(self, lines: tuple[OrderLine, ...], tier: str) -> int:
        amount = self.subtotal(lines)
        if tier == "gold":
            amount -= amount * self.settings.gold_discount_percent // 100
        return amount

    def shipping_fee(self, total_cents: int) -> int:
        return 0 if total_cents >= self.settings.free_shipping_threshold_cents else 599
