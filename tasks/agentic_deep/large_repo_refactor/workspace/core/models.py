"""Plain records stored in the registries."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Customer:
    id: str
    email: str
    name: str
    tier: str = "standard"


@dataclass(frozen=True)
class Product:
    sku: str
    name: str
    price_cents: int


@dataclass(frozen=True)
class OrderLine:
    sku: str
    quantity: int
    unit_price_cents: int

    @property
    def total_cents(self) -> int:
        return self.quantity * self.unit_price_cents


@dataclass
class Order:
    id: str
    customer_id: str
    lines: tuple[OrderLine, ...]
    total_cents: int
    status: str = "created"
    created_at: int = 0
    history: list[str] = field(default_factory=list)

    def line_summary(self) -> list[tuple[str, int]]:
        return [(line.sku, line.quantity) for line in self.lines]


@dataclass
class Payment:
    id: str
    order_id: str
    amount_cents: int
    status: str = "captured"


@dataclass
class Shipment:
    id: str
    order_id: str
    carrier: str
    status: str = "dispatched"
