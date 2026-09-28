"""Exchange rates and conversion between currencies."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from ledger.errors import CurrencyError
from ledger.money import quantize


def normalise_code(code: str) -> str:
    """Upper-case a three-letter currency code, or raise CurrencyError."""
    text = str(code).strip() if isinstance(code, str) else ""
    if len(text) != 3 or not text.isascii() or not text.isalpha():
        raise CurrencyError(f"invalid currency code: {code!r}")
    return text.upper()


class RateTable:
    """Rates express one unit of a currency in the base currency."""

    def __init__(self, base: str = "USD") -> None:
        self.base = normalise_code(base)
        self._rates: dict[str, Decimal] = {}

    def set_rate(self, code: str, rate: Decimal | int | str) -> None:
        key = normalise_code(code)
        if key == self.base:
            raise CurrencyError("cannot set a rate for the base currency")
        try:
            value = Decimal(str(rate))
        except InvalidOperation as exc:
            raise CurrencyError(f"invalid rate: {rate!r}") from exc
        if not value.is_finite() or value <= 0:
            raise CurrencyError("rate must be positive")
        self._rates[key] = value

    def rate(self, code: str) -> Decimal:
        key = normalise_code(code)
        if key == self.base:
            return Decimal(1)
        try:
            return self._rates[key]
        except KeyError:
            raise CurrencyError(f"unknown currency: {key}") from None

    def convert(self, amount: Decimal, from_code: str, to_code: str) -> Decimal:
        source, target = normalise_code(from_code), normalise_code(to_code)
        if source == target:
            return amount
        return quantize(Decimal(amount) * self.rate(source) / self.rate(target))

    def rates(self) -> dict[str, Decimal]:
        return dict(sorted(self._rates.items()))

    def currencies(self) -> list[str]:
        return sorted({self.base, *self._rates})
