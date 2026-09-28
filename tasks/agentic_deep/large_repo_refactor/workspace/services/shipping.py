"""Shipments."""

from __future__ import annotations

from core import events
from core.constants import EVENT_SHIPMENT_DELIVERED, EVENT_SHIPMENT_DISPATCHED
from core.constants import SUPPORTED_CARRIERS
from core.errors import InvalidTransition, ValidationError
from core.ids import IdGenerator
from core.models import Shipment
from core.registry import Registry
from services.orders import OrderService


class ShippingService:
    def __init__(self, shipments: Registry[Shipment], ids: IdGenerator, orders: OrderService) -> None:
        self.shipments = shipments
        self.ids = ids
        self.orders = orders

    def dispatch(self, order_id: str, carrier: str) -> Shipment:
        if carrier not in SUPPORTED_CARRIERS:
            raise ValidationError(f"unsupported carrier: {carrier}")
        order = self.orders.get(order_id)
        if order.status != "paid":
            raise InvalidTransition("order", order.id, order.status, "shipped")
        shipment = self.shipments.add(Shipment(id=self.ids.next(), order_id=order.id, carrier=carrier))
        events.emit(EVENT_SHIPMENT_DISPATCHED, {"shipment_id": shipment.id, "order_id": order.id, "carrier": carrier})
        self.orders.mark_shipped(order.id, shipment.id)
        return shipment

    def deliver(self, shipment_id: str) -> Shipment:
        shipment = self.shipments.get(shipment_id)
        if shipment.status != "dispatched":
            raise InvalidTransition("shipment", shipment.id, shipment.status, "delivered")
        shipment.status = "delivered"
        events.emit(EVENT_SHIPMENT_DELIVERED, {"shipment_id": shipment.id, "order_id": shipment.order_id})
        return shipment
