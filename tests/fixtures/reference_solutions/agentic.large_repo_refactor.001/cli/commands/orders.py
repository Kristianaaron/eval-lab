"""The scripted demo flow used by ``shop demo``."""

from __future__ import annotations

from typing import TextIO

from core.events import Event, EventType
from core.errors import PaymentDeclined


def seed_catalog(app) -> None:
    catalog, inventory = app.services.catalog, app.services.inventory
    catalog.add_product("kb-01", "Keyboard", 4_999)
    catalog.add_product("ms-02", "Mouse", 1_999)
    catalog.add_product("mn-03", "Monitor", 24_999)
    inventory.receive("kb-01", 10)
    inventory.receive("ms-02", 4)
    inventory.receive("mn-03", 2)


def run_demo(app, out: TextIO) -> None:
    seed_catalog(app)
    services = app.services
    alice = services.customers.register("alice@example.test", "Alice")
    bob = services.customers.register("bob@example.test", "Bob")
    services.customers.upgrade(alice.id, "gold")
    # the demo also announces the upgrade on the "marketing" side of the house
    app.bus.publish(Event(EventType.CUSTOMER_UPGRADED, {"customer_id": alice.id, "tier": "gold", "previous": "gold", "source": "demo"}))

    services.carts.add_item(alice.id, "kb-01", 2)
    services.carts.add_item(alice.id, "ms-02", 1)
    order = services.orders.create_order(alice.id)
    services.payments.capture(order.id, "4242")
    shipment = services.shipping.dispatch(order.id, "ups")
    services.shipping.deliver(shipment.id)

    services.carts.add_item(bob.id, "mn-03", 1)
    declined = services.orders.create_order(bob.id)
    try:
        services.payments.capture(declined.id, "0000")
    except PaymentDeclined as exc:
        out.write(f"{exc}\n")

    out.write(f"{order.id} {services.orders.get(order.id).status} total={order.total_cents}\n")
    out.write(f"{declined.id} {services.orders.get(declined.id).status} total={declined.total_cents}\n")
    out.write(f"notifications={len(services.notifications.outbox)}\n")
    out.write(f"audit={len(app.plugins['audit'].entries)}\n")
