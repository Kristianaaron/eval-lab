"""Application services. Each one takes its collaborators explicitly."""

from __future__ import annotations

from dataclasses import dataclass

from services.carts import CartService
from services.catalog import CatalogService
from services.customers import CustomerService
from services.inventory import InventoryService
from services.notifications import NotificationService
from services.orders import OrderService
from services.payments import PaymentService
from services.pricing import PricingService
from services.returns import ReturnsService
from services.shipping import ShippingService


@dataclass
class Services:
    customers: CustomerService
    catalog: CatalogService
    inventory: InventoryService
    pricing: PricingService
    carts: CartService
    orders: OrderService
    payments: PaymentService
    shipping: ShippingService
    returns: ReturnsService
    notifications: NotificationService

    def __iter__(self):
        return iter(
            (
                self.customers,
                self.catalog,
                self.inventory,
                self.pricing,
                self.carts,
                self.orders,
                self.payments,
                self.shipping,
                self.returns,
                self.notifications,
            )
        )
