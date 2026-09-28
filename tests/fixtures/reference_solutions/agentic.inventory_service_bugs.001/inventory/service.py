"""The application service: the only entry point the CLI and reports use."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Callable, Iterable

from inventory import pricing
from inventory.config import Settings
from inventory.errors import InsufficientStockError, ValidationError
from inventory.models import Page, Product, Quote, StockMovement
from inventory.repository import InMemoryRepository
from inventory.utils import UTC, paginate, parse_timestamp

Clock = Callable[[], datetime]


def _utc_now() -> datetime:
    return datetime.now(UTC)


class InventoryService:
    def __init__(
        self,
        repo: InMemoryRepository | None = None,
        settings: Settings | None = None,
        clock: Clock | None = None,
    ) -> None:
        self.repo = repo if repo is not None else InMemoryRepository()
        self.settings = settings or Settings(data_path=":memory:")
        self._clock = clock or _utc_now

    # -- products -----------------------------------------------------------
    def add_product(
        self,
        sku: str,
        name: str,
        unit_price: Decimal | str | int,
        category: str = "general",
        tags: Iterable[str] = (),
    ) -> Product:
        product = Product(
            sku=sku,
            name=name,
            unit_price=Decimal(str(unit_price)),
            category=category,
            tags=tuple(tags),
        )
        return self.repo.add_product(product)

    def get_product(self, sku: str) -> Product:
        return self.repo.get_product(sku)

    def list_products(
        self, page: int = 1, page_size: int | None = None, category: str | None = None
    ) -> Page[Product]:
        size = page_size if page_size is not None else self.settings.page_size
        return paginate(self.repo.list_products(category=category), page, size)

    # -- stock --------------------------------------------------------------
    def receive(
        self,
        sku: str,
        quantity: int,
        at: datetime | str | None = None,
        reason: str = "receipt",
        reference: str | None = None,
    ) -> StockMovement:
        if quantity < 1:
            raise ValidationError("received quantity must be >= 1")
        product = self.repo.get_product(sku)
        movement = StockMovement(
            sku=product.sku,
            quantity=quantity,
            recorded_at=self._resolve_time(at),
            reason=reason,
            reference=reference,
        )
        return self.repo.record_movement(movement)

    def ship(
        self,
        sku: str,
        quantity: int,
        at: datetime | str | None = None,
        reason: str = "shipment",
        reference: str | None = None,
    ) -> StockMovement:
        if quantity < 1:
            raise ValidationError("shipped quantity must be >= 1")
        product = self.repo.get_product(sku)
        available = self.repo.stock_level(product.sku)
        if quantity > available:
            raise InsufficientStockError(product.sku, quantity, available)
        movement = StockMovement(
            sku=product.sku,
            quantity=-quantity,
            recorded_at=self._resolve_time(at),
            reason=reason,
            reference=reference,
        )
        return self.repo.record_movement(movement)

    def adjust(self, sku: str, delta: int, reason: str = "adjustment") -> StockMovement:
        """Correct the on-hand count after a physical stock take."""
        if delta == 0:
            raise ValidationError("adjustment must be non-zero")
        product = self.repo.get_product(sku)
        if self.repo.stock_level(product.sku) + delta < 0:
            raise ValidationError("adjustment would make stock negative")
        movement = StockMovement(
            sku=product.sku, quantity=delta, recorded_at=self._resolve_time(None), reason=reason
        )
        return self.repo.record_movement(movement)

    def stock_level(self, sku: str) -> int:
        return self.repo.stock_level(sku)

    def movements_since(
        self, cutoff: datetime | str, sku: str | None = None
    ) -> list[StockMovement]:
        """Movements recorded at or after ``cutoff`` (inclusive), oldest first."""
        since = self._resolve_time(cutoff)
        rows = [m for m in self.repo.movements(sku) if m.recorded_at >= since]
        return sorted(rows, key=lambda m: m.recorded_at)

    def low_stock(self, threshold: int | None = None) -> list[tuple[Product, int]]:
        """Products whose on-hand quantity is at or below ``threshold``."""
        limit = threshold if threshold is not None else self.settings.low_stock_threshold
        levels = self.repo.stock_levels()
        return [
            (product, levels.get(product.sku, 0))
            for product in self.repo.list_products()
            if levels.get(product.sku, 0) <= limit
        ]

    # -- pricing ------------------------------------------------------------
    def quote(self, sku: str, quantity: int) -> Quote:
        product = self.repo.get_product(sku)
        return pricing.quote(
            product,
            quantity,
            rules=self.settings.discount_rules,
            tax_rate=self.settings.tax_rate,
        )

    # -- helpers ------------------------------------------------------------
    def _resolve_time(self, value: datetime | str | None) -> datetime:
        if value is None:
            now = self._clock()
            if now.tzinfo is None:
                raise ValidationError("clock must return timezone-aware datetimes")
            return now
        if isinstance(value, str):
            return parse_timestamp(value)
        if value.tzinfo is None:
            raise ValidationError("timestamps must be timezone-aware")
        return value
