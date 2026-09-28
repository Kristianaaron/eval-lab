import unittest

from core.errors import PaymentDeclined, ValidationError
from tests.helpers import app_with_catalog, customer_with_cart


class PaymentTests(unittest.TestCase):
    def test_declined_card(self):
        app = app_with_catalog()
        customer = customer_with_cart(app)
        order = app.services.orders.create_order(customer.id)
        with self.assertRaises(PaymentDeclined):
            app.services.payments.capture(order.id, "0000")
        self.assertEqual(order.status, "created")
        self.assertEqual(app.plugins["metrics"].snapshot(), {"order.created": 1, "payment.failed": 1})
        self.assertEqual(app.services.notifications.sent_via("sms"), [
            "Payment for ord-0001 failed: card declined",
        ])
        self.assertEqual(app.plugins["slack_alerts"].alerts[-1], "payment failed for ord-0001: card declined")
        payment = app.services.payments.capture(order.id, "4242")
        self.assertEqual(payment.amount_cents, order.total_cents)

    def test_return_refunds_and_restocks(self):
        app = app_with_catalog()
        customer = customer_with_cart(app)
        order = app.services.orders.create_order(customer.id)
        app.services.payments.capture(order.id, "4242")
        shipment = app.services.shipping.dispatch(order.id, "fedex")
        app.services.shipping.deliver(shipment.id)
        points_before = app.plugins["loyalty"].points[customer.id]
        refunded = app.services.returns.process_return(order.id)
        self.assertEqual(refunded, ["pay-0001"])
        self.assertEqual(order.status, "returned")
        self.assertEqual(app.services.inventory.available("kb-01"), 10)
        self.assertEqual(app.plugins["loyalty"].points[customer.id], 0)
        self.assertGreater(points_before, 0)
        self.assertEqual(app.services.notifications.sent_via("email")[-1], "Refund of 11997 cents for ord-0001")
        with self.assertRaises(ValidationError):
            app.services.returns.process_return(order.id)


class CustomerTests(unittest.TestCase):
    def test_registration_and_upgrade(self):
        app = app_with_catalog()
        alice = app.services.customers.register("alice@example.test", "Alice Liddell")
        with self.assertRaises(ValidationError):
            app.services.customers.register("alice@example.test", "Again")
        app.services.customers.upgrade(alice.id, "gold")
        self.assertEqual(app.plugins["search_indexer"].index[alice.id], {
            "name": "Alice Liddell", "email": "alice@example.test", "tier": "gold",
        })
        self.assertEqual(app.plugins["search_indexer"].search("liddell"), [alice.id])
        self.assertEqual(app.plugins["loyalty"].points[alice.id], 100)
        self.assertEqual(app.plugins["cache_invalidator"].invalidated, [f"customer:{alice.id}"])
        self.assertEqual(app.plugins["analytics"].signups, 1)


if __name__ == "__main__":
    unittest.main()
