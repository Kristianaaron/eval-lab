"""Plain data records used throughout the package."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Generic, TypeVar

from inventory.errors import ValidationError

T = TypeVar("T")


@dataclass(frozen=True)
class Product:
    """A stock keeping unit and its list price."""

    sku: str
    name: str
    unit_price: Decimal
    category: str = "general"
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.sku or not self.sku.strip():
            raise ValidationError("sku must not be empty")
        if not self.name or not self.name.strip():
            raise ValidationError("name must not be empty")
        try:
            price = Decimal(str(self.unit_price))
        except (InvalidOperation, ValueError) as exc:
            raise ValidationError(f"invalid unit price: {self.unit_price!r}") from exc
        if price < 0:
            raise ValidationError("unit price must not be negative")
        object.__setattr__(self, "unit_price", price)
        object.__setattr__(self, "sku", self.sku.strip().upper())
        object.__setattr__(self, "tags", tuple(self.tags))


@dataclass(frozen=True)
class StockMovement:
    """One change to the on-hand quantity of a SKU.

    ``quantity`` is positive for receipts and negative for shipments or
    write-offs. ``recorded_at`` must be timezone-aware (UTC by convention).
    """

    sku: str
    quantity: int
    recorded_at: datetime
    reason: str = ""
    reference: str | None = None

    def __post_init__(self) -> None:
        if self.quantity == 0:
            raise ValidationError("a stock movement must change the quantity")
        if self.recorded_at.tzinfo is None:
            raise ValidationError("recorded_at must be timezone-aware")
        object.__setattr__(self, "sku", self.sku.strip().upper())


@dataclass(frozen=True)
class Page(Generic[T]):
    """One page of a paginated listing."""

    items: tuple[T, ...]
    page: int
    page_size: int
    total: int

    @property
    def pages(self) -> int:
        return max(1, math.ceil(self.total / self.page_size))

    @property
    def has_next(self) -> bool:
        return self.page < self.pages

    @property
    def has_previous(self) -> bool:
        return self.page > 1


@dataclass(frozen=True)
class Quote:
    """The result of pricing ``quantity`` units of a product."""

    product: Product
    quantity: int
    list_unit_price: Decimal
    unit_price: Decimal
    subtotal: Decimal
    tax: Decimal
    total: Decimal
    rule_name: str | None = None
