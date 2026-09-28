"""Product catalogue."""

from __future__ import annotations

from core.errors import ValidationError
from core.models import Product
from core.registry import Registry


class CatalogService:
    def __init__(self, bus, products: Registry[Product]) -> None:
        self.bus = bus
        self.products = products

    def add_product(self, sku: str, name: str, price_cents: int) -> Product:
        if price_cents <= 0:
            raise ValidationError("price must be positive")
        return self.products.add(Product(sku=sku, name=name, price_cents=price_cents))

    def get(self, sku: str) -> Product:
        return self.products.get(sku)

    def skus(self) -> list[str]:
        return sorted(p.sku for p in self.products)
