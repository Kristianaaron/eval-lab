"""Shared fixtures for the visible suite (API-agnostic: only public services are used)."""

from app import build_app


def app_with_catalog():
    app = build_app()
    catalog, inventory = app.services.catalog, app.services.inventory
    catalog.add_product("kb-01", "Keyboard", 4_999)
    catalog.add_product("ms-02", "Mouse", 1_999)
    catalog.add_product("mn-03", "Monitor", 24_999)
    inventory.receive("kb-01", 10)
    inventory.receive("ms-02", 4)
    inventory.receive("mn-03", 2)
    return app


def customer_with_cart(app, email="alice@example.test", items=(("kb-01", 2), ("ms-02", 1))):
    customer = app.services.customers.register(email, email.split("@")[0].title())
    for sku, qty in items:
        app.services.carts.add_item(customer.id, sku, qty)
    return customer
