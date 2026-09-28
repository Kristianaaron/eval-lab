"""Exception hierarchy for the inventory package.

Every error raised on purpose by this package derives from
:class:`InventoryError`, so callers (and the CLI) can catch one type and
turn it into a friendly message.
"""

from __future__ import annotations


class InventoryError(Exception):
    """Base class for every error raised by the inventory package."""


class ConfigError(InventoryError):
    """The settings file is missing, unreadable or malformed."""


class NotFoundError(InventoryError):
    """A product (or other record) does not exist."""


class ValidationError(InventoryError):
    """User supplied input that does not make sense."""


class InsufficientStockError(InventoryError):
    """A shipment asked for more units than are on hand."""

    def __init__(self, sku: str, requested: int, available: int) -> None:
        self.sku = sku
        self.requested = requested
        self.available = available
        super().__init__(
            f"cannot ship {requested} x {sku}: only {available} on hand"
        )
