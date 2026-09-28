"""Per-customer shopping carts."""

from __future__ import annotations

from core import events
from core.constants import EVENT_CART_ITEM_ADDED
from core.constants import MAX_LINES_PER_ORDER
from core.errors import ValidationError
from core.models import OrderLine
from services.catalog import CatalogService


class CartService:
    def __init__(self, catalog: CatalogService) -> None:
        self.catalog = catalog
        self._carts: dict[str, dict[str, int]] = {}

    def add_item(self, customer_id: str, sku: str, quantity: int = 1) -> int:
        if quantity <= 0:
            raise ValidationError("quantity must be positive")
        product = self.catalog.get(sku)
        cart = self._carts.setdefault(customer_id, {})
        if sku not in cart and len(cart) >= MAX_LINES_PER_ORDER:
            raise ValidationError("too many distinct items in cart")
        cart[sku] = cart.get(sku, 0) + quantity
        events.emit(EVENT_CART_ITEM_ADDED, {"customer_id": customer_id, "sku": product.sku, "quantity": quantity, "in_cart": cart[sku]})
        return cart[sku]

    def lines(self, customer_id: str) -> tuple[OrderLine, ...]:
        cart = self._carts.get(customer_id, {})
        return tuple(
            OrderLine(sku=sku, quantity=qty, unit_price_cents=self.catalog.get(sku).price_cents)
            for sku, qty in sorted(cart.items())
        )

    def clear(self, customer_id: str) -> None:
        self._carts.pop(customer_id, None)
