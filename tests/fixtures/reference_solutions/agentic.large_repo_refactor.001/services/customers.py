"""Customer registration and tier upgrades."""

from __future__ import annotations

from core.events import Event, EventType
from core.errors import ValidationError
from core.ids import IdGenerator
from core.models import Customer
from core.registry import Registry

TIERS = ("standard", "silver", "gold")


class CustomerService:
    def __init__(self, bus, customers: Registry[Customer], ids: IdGenerator) -> None:
        self.bus = bus
        self.customers = customers
        self.ids = ids

    def register(self, email: str, name: str) -> Customer:
        if "@" not in email:
            raise ValidationError(f"invalid email: {email}")
        if any(c.email == email for c in self.customers):
            raise ValidationError(f"email already registered: {email}")
        customer = self.customers.add(Customer(id=self.ids.next(), email=email, name=name))
        self.bus.publish(Event(EventType.CUSTOMER_REGISTERED, {"customer_id": customer.id, "email": email, "name": name}))
        return customer

    def upgrade(self, customer_id: str, tier: str) -> Customer:
        if tier not in TIERS:
            raise ValidationError(f"unknown tier: {tier}")
        customer = self.customers.get(customer_id)
        previous = customer.tier
        customer.tier = tier
        self.bus.publish(Event(EventType.CUSTOMER_UPGRADED, {"customer_id": customer.id, "tier": tier, "previous": previous}))
        return customer

    def get(self, customer_id: str) -> Customer:
        return self.customers.get(customer_id)
