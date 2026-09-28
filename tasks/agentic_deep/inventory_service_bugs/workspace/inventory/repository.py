"""Storage back-ends.

:class:`InMemoryRepository` keeps everything in process memory and is the
base for :class:`JsonFileRepository`, which additionally persists the same
state to a single JSON document.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable

from inventory.errors import NotFoundError, ValidationError
from inventory.models import Product, StockMovement
from inventory.utils import format_timestamp, normalise_sku, parse_timestamp


class InMemoryRepository:
    """Products keyed by SKU plus an append-only list of stock movements."""

    def __init__(
        self,
        products: Iterable[Product] | None = None,
        movements: Iterable[StockMovement] | None = None,
    ) -> None:
        self._products: dict[str, Product] = {}
        self._movements: list[StockMovement] = []
        for product in products or ():
            self.add_product(product)
        for movement in movements or ():
            self.record_movement(movement)

    # -- products -----------------------------------------------------------
    def add_product(self, product: Product) -> Product:
        if product.sku in self._products:
            raise ValidationError(f"product {product.sku} already exists")
        self._products[product.sku] = product
        return product

    def get_product(self, sku: str) -> Product:
        key = normalise_sku(sku)
        try:
            return self._products[key]
        except KeyError:
            raise NotFoundError(f"unknown product: {key}") from None

    def has_product(self, sku: str) -> bool:
        return normalise_sku(sku) in self._products

    def remove_product(self, sku: str) -> None:
        key = normalise_sku(sku)
        if key not in self._products:
            raise NotFoundError(f"unknown product: {key}")
        del self._products[key]
        self._movements = [m for m in self._movements if m.sku != key]

    def list_products(self, category: str | None = None) -> list[Product]:
        products = self._products.values()
        if category is not None:
            products = (p for p in products if p.category == category)
        return sorted(products, key=lambda p: p.sku)

    # -- movements ----------------------------------------------------------
    def record_movement(self, movement: StockMovement) -> StockMovement:
        if movement.sku not in self._products:
            raise NotFoundError(f"unknown product: {movement.sku}")
        self._movements.append(movement)
        return movement

    def movements(self, sku: str | None = None) -> list[StockMovement]:
        if sku is None:
            return list(self._movements)
        key = normalise_sku(sku)
        return [m for m in self._movements if m.sku == key]

    def stock_level(self, sku: str) -> int:
        key = normalise_sku(sku)
        if key not in self._products:
            raise NotFoundError(f"unknown product: {key}")
        return sum(m.quantity for m in self._movements if m.sku == key)

    def stock_levels(self) -> dict[str, int]:
        levels = {sku: 0 for sku in self._products}
        for movement in self._movements:
            levels[movement.sku] = levels.get(movement.sku, 0) + movement.quantity
        return levels


class JsonFileRepository(InMemoryRepository):
    """An in-memory repository mirrored to a JSON file on :meth:`save`."""

    def __init__(self, path: str | Path) -> None:
        super().__init__()
        self.path = Path(path)
        if self.path.exists():
            self._load()

    def save(self) -> None:
        document = {
            "products": [encode_product(p) for p in self.list_products()],
            "movements": [encode_movement(m) for m in self._movements],
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(document, indent=2, sort_keys=True), encoding="utf-8")

    def _load(self) -> None:
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        for item in raw.get("products", []):
            self.add_product(decode_product(item))
        for item in raw.get("movements", []):
            self.record_movement(decode_movement(item))


def encode_product(product: Product) -> dict[str, Any]:
    return {
        "sku": product.sku,
        "name": product.name,
        "unit_price": str(product.unit_price),
        "category": product.category,
        "tags": list(product.tags),
    }


def decode_product(raw: dict[str, Any]) -> Product:
    return Product(
        sku=raw["sku"],
        name=raw["name"],
        unit_price=Decimal(raw["unit_price"]),
        category=raw.get("category", "general"),
        tags=tuple(raw.get("tags", ())),
    )


def encode_movement(movement: StockMovement) -> dict[str, Any]:
    return {
        "sku": movement.sku,
        "quantity": movement.quantity,
        "recorded_at": format_timestamp(movement.recorded_at),
        "reason": movement.reason,
        "reference": movement.reference,
    }


def decode_movement(raw: dict[str, Any]) -> StockMovement:
    return StockMovement(
        sku=raw["sku"],
        quantity=int(raw["quantity"]),
        recorded_at=parse_timestamp(raw["recorded_at"]),
        reason=raw.get("reason", ""),
        reference=raw.get("reference"),
    )
