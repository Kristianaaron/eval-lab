"""Application assembly: registries, services and plugins wired together."""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field

from core.events import EventBus
from core.clock import Clock
from core.config import DEFAULT_SETTINGS, Settings
from core.ids import IdGenerator
from core.models import Customer, Order, Payment, Product, Shipment
from core.registry import Registry
from plugins import PLUGIN_MODULES
from services import Services
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
class App:
    settings: Settings
    clock: Clock
    bus: EventBus
    services: Services | None = None
    plugins: dict[str, object] = field(default_factory=dict)


def build_app(bus: EventBus | None = None, settings: Settings | None = None) -> App:
    """Create a fully wired application."""
    settings = settings or DEFAULT_SETTINGS
    bus = bus if bus is not None else EventBus()
    clock = Clock()
    app = App(settings=settings, clock=clock, bus=bus)

    customers = CustomerService(bus, Registry("customer", lambda c: c.id), IdGenerator("cus"))
    catalog = CatalogService(bus, Registry("product", lambda p: p.sku))
    inventory = InventoryService(bus, settings)
    pricing = PricingService(bus, settings)
    carts = CartService(bus, catalog)
    orders = OrderService(
        bus,
        Registry("order", lambda o: o.id), IdGenerator("ord"), clock, carts, pricing, inventory, customers
    )
    payments = PaymentService(bus, Registry("payment", lambda p: p.id), IdGenerator("pay"), orders)
    shipping = ShippingService(bus, Registry("shipment", lambda s: s.id), IdGenerator("shp"), orders)
    returns = ReturnsService(bus, orders, inventory, payments)
    notifications = NotificationService(bus)
    app.services = Services(
        customers=customers,
        catalog=catalog,
        inventory=inventory,
        pricing=pricing,
        carts=carts,
        orders=orders,
        payments=payments,
        shipping=shipping,
        returns=returns,
        notifications=notifications,
    )

    for module_name in PLUGIN_MODULES:
        module = importlib.import_module(module_name)
        plugin = module.register(app)
        app.plugins[getattr(plugin, "name", module_name.rsplit(".", 1)[-1])] = plugin
    return app
