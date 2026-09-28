"""Card payments (a fake gateway: card ``0000`` is always declined)."""

from __future__ import annotations

from core.events import Event, EventType
from core.errors import PaymentDeclined, ValidationError
from core.ids import IdGenerator
from core.models import Payment
from core.registry import Registry
from services.orders import OrderService

DECLINED_CARD = "0000"


class PaymentService:
    def __init__(self, bus, payments: Registry[Payment], ids: IdGenerator, orders: OrderService) -> None:
        self.bus = bus
        self.payments = payments
        self.ids = ids
        self.orders = orders

    def capture(self, order_id: str, card_last4: str) -> Payment:
        order = self.orders.get(order_id)
        if order.status != "created":
            raise ValidationError(f"order {order.id} is {order.status}, cannot capture")
        if card_last4 == DECLINED_CARD:
            self.bus.publish(Event(EventType.PAYMENT_FAILED, {"order_id": order.id, "amount_cents": order.total_cents, "reason": "card declined"}))
            raise PaymentDeclined(order.id, "card declined")
        payment = self.payments.add(Payment(id=self.ids.next(), order_id=order.id, amount_cents=order.total_cents))
        self.bus.publish(Event(EventType.PAYMENT_CAPTURED, {"payment_id": payment.id, "order_id": order.id, "amount_cents": payment.amount_cents}))
        self.orders.mark_paid(order.id)
        return payment

    def refund(self, payment_id: str) -> Payment:
        payment = self.payments.get(payment_id)
        if payment.status != "captured":
            raise ValidationError(f"payment {payment.id} is {payment.status}, cannot refund")
        payment.status = "refunded"
        self.bus.publish(Event(EventType.PAYMENT_REFUNDED, {"payment_id": payment.id, "order_id": payment.order_id, "amount_cents": payment.amount_cents}))
        return payment

    def for_order(self, order_id: str) -> list[Payment]:
        return [p for p in self.payments if p.order_id == order_id]
