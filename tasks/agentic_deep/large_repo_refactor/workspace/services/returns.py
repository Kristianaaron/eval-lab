"""Returns: refund the payment and put the stock back."""

from __future__ import annotations

from core.errors import ValidationError
from services.inventory import InventoryService
from services.orders import OrderService
from services.payments import PaymentService


class ReturnsService:
    def __init__(self, orders: OrderService, inventory: InventoryService, payments: PaymentService) -> None:
        self.orders = orders
        self.inventory = inventory
        self.payments = payments
        self.returned: list[str] = []

    def process_return(self, order_id: str) -> list[str]:
        order = self.orders.get(order_id)
        if order.status != "shipped":
            raise ValidationError(f"order {order.id} is {order.status}, cannot be returned")
        refunded = []
        for payment in self.payments.for_order(order.id):
            if payment.status == "captured":
                refunded.append(self.payments.refund(payment.id).id)
        order.status = "returned"
        order.history.append("returned")
        for sku, quantity in order.line_summary():
            self.inventory.receive(sku, quantity)
        self.returned.append(order.id)
        return refunded
