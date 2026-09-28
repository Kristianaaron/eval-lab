"""Stock levels and reservations."""

from __future__ import annotations

from core.events import Event, EventType
from core.config import Settings
from core.errors import InsufficientStock, ValidationError
from core.models import OrderLine


class InventoryService:
    def __init__(self, bus, settings: Settings) -> None:
        self.bus = bus
        self.settings = settings
        self.stock: dict[str, int] = {}
        self.reservations: dict[str, list[tuple[str, int]]] = {}

    def receive(self, sku: str, quantity: int) -> int:
        if quantity <= 0:
            raise ValidationError("received quantity must be positive")
        self.stock[sku] = self.stock.get(sku, 0) + quantity
        return self.stock[sku]

    def available(self, sku: str) -> int:
        return self.stock.get(sku, 0)

    def reserve(self, order_id: str, lines: tuple[OrderLine, ...]) -> None:
        for line in lines:
            available = self.available(line.sku)
            if line.quantity > available:
                raise InsufficientStock(line.sku, line.quantity, available)
        summary = []
        for line in lines:
            self.stock[line.sku] -= line.quantity
            summary.append((line.sku, line.quantity))
        self.reservations[order_id] = summary
        self.bus.publish(Event(EventType.INVENTORY_RESERVED, {"order_id": order_id, "lines": list(summary)}))
        for sku, _ in summary:
            remaining = self.stock[sku]
            if remaining <= self.settings.low_stock_threshold:
                self.bus.publish(Event(EventType.INVENTORY_LOW, {"sku": sku, "remaining": remaining, "threshold": self.settings.low_stock_threshold}))

    def release(self, order_id: str) -> list[tuple[str, int]]:
        summary = self.reservations.pop(order_id, [])
        for sku, quantity in summary:
            self.stock[sku] = self.stock.get(sku, 0) + quantity
        if summary:
            self.bus.publish(Event(EventType.INVENTORY_RELEASED, {"order_id": order_id, "lines": list(summary)}))
        return summary
