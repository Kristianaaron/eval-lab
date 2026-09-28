"""Plain-text reports rendered from an :class:`InventoryService`."""

from __future__ import annotations

from datetime import datetime

from inventory.service import InventoryService
from inventory.utils import format_money, format_timestamp


def stock_report(service: InventoryService) -> str:
    """One line per product: ``SKU  NAME  ON_HAND``."""
    levels = service.repo.stock_levels()
    products = service.repo.list_products()
    if not products:
        return "(no products)"
    width = max(len(p.name) for p in products)
    lines = [f"{'SKU':<10} {'NAME':<{width}} {'ON HAND':>8}"]
    for product in products:
        lines.append(f"{product.sku:<10} {product.name:<{width}} {levels.get(product.sku, 0):>8}")
    return "\n".join(lines)


def low_stock_report(service: InventoryService, threshold: int | None = None) -> str:
    rows = service.low_stock(threshold)
    if not rows:
        return "All products are above the low-stock threshold."
    lines = ["Low stock:"]
    for product, level in rows:
        lines.append(f"  {product.sku:<10} {level:>5}  {product.name}")
    return "\n".join(lines)


def movement_log(service: InventoryService, since: datetime | str) -> str:
    rows = service.movements_since(since)
    if not rows:
        return "(no movements)"
    lines = []
    for movement in rows:
        sign = "+" if movement.quantity > 0 else ""
        lines.append(
            f"{format_timestamp(movement.recorded_at)}  {movement.sku:<10} "
            f"{sign}{movement.quantity:>5}  {movement.reason}"
        )
    return "\n".join(lines)


def quote_report(service: InventoryService, sku: str, quantity: int) -> str:
    q = service.quote(sku, quantity)
    currency = service.settings.currency
    lines = [
        f"{q.quantity} x {q.product.name} ({q.product.sku})",
        f"  list price:  {format_money(q.list_unit_price, currency)}",
        f"  unit price:  {format_money(q.unit_price, currency)}"
        + (f"  [{q.rule_name}]" if q.rule_name else ""),
        f"  subtotal:    {format_money(q.subtotal, currency)}",
        f"  tax:         {format_money(q.tax, currency)}",
        f"  total:       {format_money(q.total, currency)}",
    ]
    return "\n".join(lines)
