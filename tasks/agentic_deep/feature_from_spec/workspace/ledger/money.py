"""Decimal helpers. Amounts are always quantized to cents, rounding half up."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from ledger.errors import ValidationError

CENT = Decimal("0.01")


def quantize(amount: Decimal | int | str) -> Decimal:
    """Round to two decimal places, half up."""
    return Decimal(amount).quantize(CENT, rounding=ROUND_HALF_UP)


def parse_amount(text: str) -> Decimal:
    """Parse ``'1,234.50'`` / ``'-3'`` into a quantized Decimal."""
    cleaned = str(text).strip().replace(",", "")
    if not cleaned:
        raise ValidationError("amount must not be empty")
    try:
        return quantize(Decimal(cleaned))
    except InvalidOperation as exc:
        raise ValidationError(f"invalid amount: {text!r}") from exc


def format_amount(amount: Decimal) -> str:
    """``Decimal('-2000')`` -> ``'-2,000.00'``."""
    return f"{quantize(amount):,.2f}"
