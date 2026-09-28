"""Typed, instance-based event dispatch.

An :class:`EventBus` holds its own subscriptions, so several applications can
coexist in one process. Events are :class:`Event` records whose ``type`` is a
member of :class:`EventType`; handlers receive the whole event.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


class EventType(Enum):
    CUSTOMER_REGISTERED = "customer.registered"
    CUSTOMER_UPGRADED = "customer.upgraded"
    CART_ITEM_ADDED = "cart.item_added"
    ORDER_CREATED = "order.created"
    ORDER_PAID = "order.paid"
    ORDER_CANCELLED = "order.cancelled"
    ORDER_SHIPPED = "order.shipped"
    INVENTORY_RESERVED = "inventory.reserved"
    INVENTORY_RELEASED = "inventory.released"
    INVENTORY_LOW = "inventory.low"
    PAYMENT_CAPTURED = "payment.captured"
    PAYMENT_FAILED = "payment.failed"
    PAYMENT_REFUNDED = "payment.refunded"
    SHIPMENT_DISPATCHED = "shipment.dispatched"
    SHIPMENT_DELIVERED = "shipment.delivered"
    NOTIFICATION_SENT = "notification.sent"


@dataclass(frozen=True)
class Event:
    type: EventType
    payload: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.type, EventType):
            raise TypeError(f"event type must be an EventType, got {self.type!r}")


Handler = Callable[[Event], None]


class EventBus:
    def __init__(self) -> None:
        self._handlers: dict[EventType, list[Handler]] = {}

    def subscribe(self, event_type: EventType, handler: Handler) -> None:
        if not isinstance(event_type, EventType):
            raise TypeError(f"expected an EventType, got {event_type!r}")
        handlers = self._handlers.setdefault(event_type, [])
        if handler not in handlers:
            handlers.append(handler)

    def unsubscribe(self, event_type: EventType, handler: Handler) -> None:
        if not isinstance(event_type, EventType):
            raise TypeError(f"expected an EventType, got {event_type!r}")
        handlers = self._handlers.get(event_type, [])
        if handler in handlers:
            handlers.remove(handler)

    def publish(self, event: Event) -> int:
        if not isinstance(event, Event):
            raise TypeError(f"expected an Event, got {event!r}")
        handlers = tuple(self._handlers.get(event.type, ()))
        for handler in handlers:
            handler(event)
        return len(handlers)

    def handlers(self, event_type: EventType) -> tuple[Handler, ...]:
        if not isinstance(event_type, EventType):
            raise TypeError(f"expected an EventType, got {event_type!r}")
        return tuple(self._handlers.get(event_type, ()))

    def clear(self) -> None:
        self._handlers.clear()


_default_bus: EventBus | None = None


def default_bus() -> EventBus:
    """A lazily created process-wide bus for code that has no injected bus."""
    global _default_bus
    if _default_bus is None:
        _default_bus = EventBus()
    return _default_bus


def reset_default_bus() -> None:
    global _default_bus
    _default_bus = None
