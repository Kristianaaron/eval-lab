import unittest

from app import build_app
from core.config import Settings
from core.errors import InsufficientStock, InvalidTransition, ValidationError
from tests.helpers import app_with_catalog, customer_with_cart


class InventoryTests(unittest.TestCase):
    def test_low_stock_alerts(self):
        app = app_with_catalog()
        customer = customer_with_cart(app, items=(("ms-02", 2),))
        app.services.orders.create_order(customer.id)
        remaining = app.services.inventory.available("ms-02")
        self.assertEqual(remaining, 2)
        self.assertEqual(app.plugins["stock_guard"].alerts, [("ms-02", 2)])
        self.assertEqual(app.plugins["slack_alerts"].alerts, ["low stock ms-02=2"])
        self.assertEqual(app.services.notifications.sent_via("ops"), ["Low stock: ms-02 (2 left)"])

    def test_insufficient_stock_leaves_everything_untouched(self):
        app = app_with_catalog()
        customer = customer_with_cart(app, items=(("mn-03", 3),))
        with self.assertRaises(InsufficientStock):
            app.services.orders.create_order(customer.id)
        self.assertEqual(app.services.inventory.available("mn-03"), 2)
        self.assertEqual(len(app.services.orders.orders), 0)
        self.assertNotIn("order.created", app.plugins["audit"].names())

    def test_cancel_releases_stock(self):
        app = app_with_catalog()
        customer = customer_with_cart(app)
        order = app.services.orders.create_order(customer.id)
        app.services.orders.cancel(order.id, "customer request")
        self.assertEqual(app.services.inventory.available("kb-01"), 10)
        self.assertEqual(app.plugins["warehouse_sync"].pending, {})
        self.assertEqual(app.plugins["reporting"].cancelled, [(order.id, "customer request")])
        with self.assertRaises(InvalidTransition):
            app.services.orders.mark_paid(order.id)


class FraudTests(unittest.TestCase):
    def test_large_orders_are_cancelled_for_review(self):
        app = app_with_catalog()
        customer = customer_with_cart(app, items=(("mn-03", 2), ("kb-01", 10)))
        order = app.services.orders.create_order(customer.id)
        self.assertGreater(order.total_cents, app.settings.fraud_limit_cents)
        self.assertEqual(order.status, "cancelled")
        self.assertEqual(app.plugins["fraud_check"].flagged, [order.id])
        self.assertEqual(app.plugins["slack_alerts"].alerts[-1], f"fraud hold on {order.id}")
        self.assertEqual(app.services.inventory.available("mn-03"), 2)
        with self.assertRaises(ValidationError):
            app.services.payments.capture(order.id, "4242")

    def test_custom_settings(self):
        app = build_app(settings=Settings(fraud_limit_cents=1))
        app.services.catalog.add_product("kb-01", "Keyboard", 4_999)
        app.services.inventory.receive("kb-01", 5)
        customer = customer_with_cart(app, items=(("kb-01", 1),))
        order = app.services.orders.create_order(customer.id)
        self.assertEqual(order.status, "cancelled")


if __name__ == "__main__":
    unittest.main()
