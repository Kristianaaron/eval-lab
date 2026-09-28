"""Order lifecycle: created -> paid -> shipped, or cancelled."""

from __future__ import annotations

from core.events import Event, EventType
from core.clock import Clock
from core.errors import InvalidTransition, ValidationError
from core.ids import IdGenerator
from core.models import Order
from core.registry import Registry
from services.carts import CartService
from services.customers import CustomerService
from services.inventory import InventoryService
from services.pricing import PricingService


class OrderService:
    def __init__(
        self,
        bus,
        orders: Registry[Order],
        ids: IdGenerator,
        clock: Clock,
        carts: CartService,
        pricing: PricingService,
        inventory: InventoryService,
        customers: CustomerService,
    ) -> None:
        self.bus = bus
        self.orders = orders
        self.ids = ids
        self.clock = clock
        self.carts = carts
        self.pricing = pricing
        self.inventory = inventory
        self.customers = customers

    def create_order(self, customer_id: str) -> Order:
        customer = self.customers.get(customer_id)
        lines = self.carts.lines(customer_id)
        if not lines:
            raise ValidationError("cart is empty")
        order = Order(
            id=self.ids.next(),
            customer_id=customer.id,
            lines=lines,
            total_cents=self.pricing.total(lines, customer.tier),
            created_at=self.clock.now(),
        )
        self.inventory.reserve(order.id, lines)
        self.orders.add(order)
        self.carts.clear(customer_id)
        order.history.append("created")
        self.bus.publish(Event(EventType.ORDER_CREATED, {"order_id": order.id, "customer_id": customer.id, "total_cents": order.total_cents, "lines": order.line_summary()}))
        return order

    def get(self, order_id: str) -> Order:
        return self.orders.get(order_id)

    def mark_paid(self, order_id: str) -> Order:
        order = self._transition(order_id, {"created"}, "paid")
        self.bus.publish(Event(EventType.ORDER_PAID, {"order_id": order.id, "customer_id": order.customer_id, "total_cents": order.total_cents}))
        return order

    def mark_shipped(self, order_id: str, shipment_id: str) -> Order:
        order = self._transition(order_id, {"paid"}, "shipped")
        self.bus.publish(Event(EventType.ORDER_SHIPPED, {"order_id": order.id, "shipment_id": shipment_id}))
        return order

    def cancel(self, order_id: str, reason: str) -> Order:
        order = self._transition(order_id, {"created", "paid"}, "cancelled")
        self.inventory.release(order.id)
        self.bus.publish(Event(EventType.ORDER_CANCELLED, {"order_id": order.id, "customer_id": order.customer_id, "reason": reason}))
        return order

    def _transition(self, order_id: str, allowed: set[str], target: str) -> Order:
        order = self.orders.get(order_id)
        if order.status not in allowed:
            raise InvalidTransition("order", order.id, order.status, target)
        order.status = target
        order.history.append(target)
        return order
