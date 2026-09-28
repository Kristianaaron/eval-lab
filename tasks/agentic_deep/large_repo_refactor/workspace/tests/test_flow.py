import unittest

from tests.helpers import app_with_catalog, customer_with_cart


class HappyPathTests(unittest.TestCase):
    def setUp(self):
        self.app = app_with_catalog()
        self.services = self.app.services
        self.alice = customer_with_cart(self.app)

    def test_order_lifecycle(self):
        order = self.services.orders.create_order(self.alice.id)
        self.assertEqual(order.id, "ord-0001")
        self.assertEqual(order.total_cents, 2 * 4_999 + 1_999)
        self.assertEqual(self.services.inventory.available("kb-01"), 8)
        self.assertEqual(self.services.inventory.available("ms-02"), 3)
        payment = self.services.payments.capture(order.id, "4242")
        self.assertEqual(payment.id, "pay-0001")
        self.assertEqual(order.status, "paid")
        shipment = self.services.shipping.dispatch(order.id, "dhl")
        self.assertEqual(order.status, "shipped")
        self.services.shipping.deliver(shipment.id)
        self.assertEqual(shipment.status, "delivered")
        self.assertEqual(order.history, ["created", "paid", "shipped"])

    def test_plugins_react_to_the_flow(self):
        order = self.services.orders.create_order(self.alice.id)
        self.services.payments.capture(order.id, "4242")
        shipment = self.services.shipping.dispatch(order.id, "ups")
        self.services.shipping.deliver(shipment.id)
        plugins = self.app.plugins
        self.assertEqual(plugins["metrics"].snapshot(), {
            "order.created": 1, "order.paid": 1, "shipment.delivered": 1,
        })
        self.assertEqual(plugins["loyalty"].points[self.alice.id], 119 * self.app.settings.loyalty_points_per_dollar)
        self.assertEqual(self.services.notifications.sent_via("email"), [
            "Order ord-0001 received", "Order ord-0001 shipped via ups",
        ])
        self.assertEqual(self.services.notifications.sent_via("sms"), ["Delivered: ord-0001"])
        self.assertEqual([name for _, name, _ in plugins["webhooks"].deliveries], ["order.paid", "shipment.dispatched"])
        self.assertEqual(plugins["warehouse_sync"].shipped, ["ord-0001"])
        self.assertEqual(plugins["warehouse_sync"].pending, {})
        self.assertEqual(plugins["reporting"].summary(), "delivered=1 cancelled=0 captured_cents=11997")
        self.assertIn("audit", plugins)
        self.assertGreaterEqual(plugins["audit"].count("notification.sent"), 3)

    def test_audit_sees_every_event_in_order(self):
        order = self.services.orders.create_order(self.alice.id)
        names = self.app.plugins["audit"].names()
        self.assertEqual(names[0], "customer.registered")
        self.assertEqual(names.count("cart.item_added"), 2)
        self.assertLess(names.index("inventory.reserved"), names.index("order.created"))
        self.assertEqual(self.app.plugins["audit"].entries[-1][0], "notification.sent")
        self.assertEqual(order.status, "created")


if __name__ == "__main__":
    unittest.main()
