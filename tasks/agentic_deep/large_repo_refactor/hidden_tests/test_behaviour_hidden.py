import io
import unittest

from app import build_app
from cli.main import main
from core.config import Settings
from core.errors import InsufficientStock, PaymentDeclined, ValidationError


def app_with_catalog(**settings):
    app = build_app(settings=Settings(**settings)) if settings else build_app()
    catalog, inventory = app.services.catalog, app.services.inventory
    catalog.add_product("kb-01", "Keyboard", 4_999)
    catalog.add_product("ms-02", "Mouse", 1_999)
    catalog.add_product("mn-03", "Monitor", 24_999)
    inventory.receive("kb-01", 10)
    inventory.receive("ms-02", 4)
    inventory.receive("mn-03", 2)
    return app


class EndToEndTests(unittest.TestCase):
    def test_gold_customer_full_lifecycle(self):
        app = app_with_catalog()
        s = app.services
        alice = s.customers.register("alice@example.test", "Alice")
        s.customers.upgrade(alice.id, "gold")
        s.carts.add_item(alice.id, "kb-01", 2)
        s.carts.add_item(alice.id, "mn-03", 1)
        order = s.orders.create_order(alice.id)
        self.assertEqual(order.total_cents, 31498)
        s.payments.capture(order.id, "4242")
        shipment = s.shipping.dispatch(order.id, "dhl")
        s.shipping.deliver(shipment.id)
        self.assertEqual(app.plugins["audit"].names(), [
            "customer.registered", "customer.upgraded", "cart.item_added", "cart.item_added",
            "inventory.reserved", "inventory.low", "notification.sent", "order.created",
            "notification.sent", "payment.captured", "order.paid", "shipment.dispatched",
            "notification.sent", "order.shipped", "notification.sent", "shipment.delivered",
            "notification.sent",
        ])
        self.assertEqual(app.plugins["metrics"].snapshot(), {"order.created": 1, "order.paid": 1, "shipment.delivered": 1})
        self.assertEqual(app.plugins["metrics"].revenue_cents, 31498)
        self.assertEqual(app.plugins["loyalty"].points, {alice.id: 100 + 314 * app.settings.loyalty_points_per_dollar})
        self.assertEqual(app.plugins["cache_invalidator"].invalidated, [f"customer:{alice.id}", f"orders:{alice.id}", "order:ord-0001", "order:ord-0001"])
        self.assertEqual(app.plugins["analytics"].popular, {"kb-01": 2, "mn-03": 1})
        self.assertEqual(app.plugins["analytics"].top_sku(), "kb-01")
        self.assertEqual(app.plugins["warehouse_sync"].shipped, ["ord-0001"])
        self.assertEqual([(n, p) for _, n, p in app.plugins["webhooks"].deliveries], [
            ("order.paid", {"order_id": "ord-0001", "customer_id": alice.id, "total_cents": 31498}),
            ("shipment.dispatched", {"shipment_id": "shp-0001", "order_id": "ord-0001", "carrier": "dhl"}),
        ])
        self.assertEqual(app.plugins["ops_dashboard"].escalations, ["ord-0001"])
        self.assertEqual(app.plugins["ops_dashboard"].notifications, 2)
        self.assertEqual(s.notifications.outbox, [
            ("ops", "#ops", "Low stock: mn-03 (1 left)"),
            ("email", "alice@example.test", "Order ord-0001 received"),
            ("email", "alice@example.test", "Order ord-0001 shipped via dhl"),
            ("sms", "alice@example.test", "Delivered: ord-0001"),
        ])
        self.assertEqual(app.plugins["stock_guard"].alerts, [("mn-03", 1)])
        self.assertEqual(app.plugins["reporting"].summary(), "delivered=1 cancelled=0 captured_cents=31498")
        self.assertEqual(app.plugins["search_indexer"].index, {alice.id: {"name": "Alice", "email": "alice@example.test", "tier": "gold"}})

        refunded = s.returns.process_return(order.id)
        self.assertEqual(refunded, ["pay-0001"])
        self.assertEqual(order.status, "returned")
        self.assertEqual(s.inventory.stock, {"kb-01": 10, "ms-02": 4, "mn-03": 2})
        self.assertEqual(app.plugins["loyalty"].points, {alice.id: 100})
        self.assertEqual(s.notifications.sent_via("email")[-1], "Refund of 31498 cents for ord-0001")
        self.assertEqual(app.plugins["audit"].names()[-3:], ["notification.sent", "payment.refunded", "notification.sent"])

    def test_fraud_hold_chains_cancellation_and_release(self):
        app = app_with_catalog()
        s = app.services
        bob = s.customers.register("bob@example.test", "Bob")
        s.carts.add_item(bob.id, "mn-03", 2)
        s.carts.add_item(bob.id, "kb-01", 10)
        order = s.orders.create_order(bob.id)
        self.assertEqual(order.status, "cancelled")
        self.assertEqual(app.plugins["fraud_check"].flagged, [order.id])
        names = app.plugins["audit"].names()
        self.assertLess(names.index("inventory.released"), names.index("order.cancelled"))
        self.assertEqual(names[-1], "order.cancelled")
        self.assertEqual(s.inventory.stock, {"kb-01": 10, "ms-02": 4, "mn-03": 2})
        self.assertEqual(app.plugins["warehouse_sync"].pending, {})
        self.assertEqual(app.plugins["stock_guard"].alerts, [])
        self.assertEqual(app.plugins["reporting"].cancelled, [(order.id, "fraud review")])
        self.assertEqual([n for _, n, _ in app.plugins["webhooks"].deliveries], ["order.cancelled"])
        self.assertEqual(app.plugins["slack_alerts"].alerts[-1], f"fraud hold on {order.id}")
        self.assertEqual(app.plugins["metrics"].snapshot(), {"order.cancelled": 1, "order.created": 1})

    def test_declined_payment_then_retry(self):
        app = app_with_catalog()
        s = app.services
        carol = s.customers.register("carol@example.test", "Carol")
        s.carts.add_item(carol.id, "kb-01", 1)
        order = s.orders.create_order(carol.id)
        with self.assertRaises(PaymentDeclined):
            s.payments.capture(order.id, "0000")
        self.assertEqual(order.status, "created")
        self.assertEqual(s.payments.for_order(order.id), [])
        self.assertEqual(s.notifications.sent_via("sms"), ["Payment for ord-0001 failed: card declined"])
        self.assertEqual(app.plugins["slack_alerts"].alerts, ["payment failed for ord-0001: card declined"])
        payment = s.payments.capture(order.id, "1111")
        self.assertEqual((payment.id, payment.amount_cents, order.status), ("pay-0001", 4_999, "paid"))
        self.assertEqual(app.plugins["metrics"].snapshot(), {"order.created": 1, "order.paid": 1, "payment.failed": 1})

    def test_insufficient_stock_and_custom_settings(self):
        app = app_with_catalog(low_stock_threshold=9, fraud_limit_cents=10_000_000)
        s = app.services
        dave = s.customers.register("dave@example.test", "Dave")
        s.carts.add_item(dave.id, "mn-03", 3)
        with self.assertRaises(InsufficientStock):
            s.orders.create_order(dave.id)
        self.assertEqual(app.plugins["audit"].count("order.created"), 0)
        s.carts.clear(dave.id)
        s.carts.add_item(dave.id, "kb-01", 2)
        s.orders.create_order(dave.id)
        self.assertEqual(app.plugins["stock_guard"].alerts, [("kb-01", 8)])
        self.assertEqual(s.notifications.sent_via("ops"), ["Low stock: kb-01 (8 left)"])
        with self.assertRaises(ValidationError):
            s.orders.create_order(dave.id)  # cart is empty again


class CliTests(unittest.TestCase):
    def test_demo_output(self):
        out = io.StringIO()
        self.assertEqual(main(["demo"], out=out), 0)
        self.assertEqual(out.getvalue(), (
            "payment for ord-0002 declined: card declined\n"
            "ord-0001 shipped total=10798\n"
            "ord-0002 created total=24999\n"
            "notifications=7\n"
            "audit=27\n"
        ))

    def test_events_output(self):
        out = io.StringIO()
        self.assertEqual(main(["events"], out=out), 0)
        self.assertEqual(out.getvalue(), (
            "customer.registered       3\n"
            "customer.upgraded         4\n"
            "cart.item_added           2\n"
            "order.created             6\n"
            "order.paid                5\n"
            "order.cancelled           6\n"
            "order.shipped             3\n"
            "inventory.reserved        2\n"
            "inventory.released        3\n"
            "inventory.low             3\n"
            "payment.captured          2\n"
            "payment.failed            4\n"
            "payment.refunded          3\n"
            "shipment.dispatched       4\n"
            "shipment.delivered        4\n"
            "notification.sent         2\n"
        ))

    def test_report_and_stock(self):
        out = io.StringIO()
        self.assertEqual(main(["report"], out=out), 0)
        self.assertEqual(out.getvalue(), "delivered=0 cancelled=0 captured_cents=0\nrevenue_cents=0\n")
        out = io.StringIO()
        self.assertEqual(main(["stock"], out=out), 0)
        self.assertEqual(out.getvalue(), "(no stock)\n")


if __name__ == "__main__":
    unittest.main()
