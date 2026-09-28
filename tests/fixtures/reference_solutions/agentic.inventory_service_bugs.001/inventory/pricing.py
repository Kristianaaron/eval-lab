"""Discount rules and money arithmetic.

All amounts are :class:`~decimal.Decimal`. Money is always rounded to two
places using *round half up* (the convention used on our invoices), never
banker's rounding and never via binary floats.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Iterable

from inventory.errors import ValidationError
from inventory.models import Product, Quote

TWO_PLACES = Decimal("0.01")

PERCENT = "percent"
FIXED = "fixed"


def money(value: Decimal | int | str) -> Decimal:
    """Round to two places, half up."""
    return Decimal(value).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class DiscountRule:
    """A discount that lowers the *unit* price of qualifying products.

    ``kind`` is ``"percent"`` (``value`` is a percentage, e.g. ``25``) or
    ``"fixed"`` (``value`` is an absolute amount taken off each unit).
    ``min_quantity`` is the smallest order quantity that qualifies and
    ``category`` restricts the rule to one product category (``None`` = any).
    """

    name: str
    kind: str
    value: Decimal
    min_quantity: int = 1
    category: str | None = None

    def __post_init__(self) -> None:
        if self.kind not in (PERCENT, FIXED):
            raise ValidationError(f"unknown discount kind: {self.kind!r}")
        object.__setattr__(self, "value", Decimal(str(self.value)))
        if self.value < 0:
            raise ValidationError("discount value must not be negative")
        if self.kind == PERCENT and self.value > 100:
            raise ValidationError("percentage discount cannot exceed 100")
        if self.min_quantity < 1:
            raise ValidationError("min_quantity must be >= 1")

    def applies_to(self, product: Product, quantity: int) -> bool:
        if quantity < self.min_quantity:
            return False
        if self.category is not None and self.category != product.category:
            return False
        return True


def discounted_unit_price(unit_price: Decimal, rule: DiscountRule) -> Decimal:
    """Unit price after applying ``rule``; never below zero."""
    if rule.kind == PERCENT:
        factor = (Decimal(100) - rule.value) / Decimal(100)
        discounted = unit_price * factor
    else:
        discounted = unit_price - rule.value
    if discounted < 0:
        discounted = Decimal(0)
    return money(discounted)


def best_rule(
    product: Product, quantity: int, rules: Iterable[DiscountRule]
) -> DiscountRule | None:
    """The applicable rule that yields the lowest unit price (first wins ties)."""
    best: DiscountRule | None = None
    best_price = product.unit_price
    for rule in rules:
        if not rule.applies_to(product, quantity):
            continue
        candidate = discounted_unit_price(product.unit_price, rule)
        if candidate < best_price:
            best, best_price = rule, candidate
    return best


def add_tax(amount: Decimal, rate_percent: Decimal) -> Decimal:
    """Tax due on ``amount`` at ``rate_percent`` percent."""
    return money(amount * Decimal(str(rate_percent)) / Decimal(100))


def quote(
    product: Product,
    quantity: int,
    rules: Iterable[DiscountRule] = (),
    tax_rate: Decimal = Decimal(0),
) -> Quote:
    """Price ``quantity`` units of ``product``."""
    if quantity < 1:
        raise ValidationError("quantity must be >= 1")
    rules = tuple(rules)
    rule = best_rule(product, quantity, rules)
    unit = discounted_unit_price(product.unit_price, rule) if rule else money(product.unit_price)
    subtotal = money(unit * quantity)
    tax = add_tax(subtotal, tax_rate)
    return Quote(
        product=product,
        quantity=quantity,
        list_unit_price=money(product.unit_price),
        unit_price=unit,
        subtotal=subtotal,
        tax=tax,
        total=money(subtotal + tax),
        rule_name=rule.name if rule else None,
    )
