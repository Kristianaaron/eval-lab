import unittest

from app import build_app

try:
    from core.events import Event, EventBus, EventType, default_bus, reset_default_bus
except ImportError:  # pragma: no cover
    Event = EventBus = EventType = default_bus = reset_default_bus = None

SUBSCRIBER_COUNTS = {
    "customer.registered": 3,
    "customer.upgraded": 4,
    "cart.item_added": 2,
    "order.created": 6,
    "order.paid": 5,
    "order.cancelled": 6,
    "order.shipped": 3,
    "inventory.reserved": 2,
    "inventory.released": 3,
    "inventory.low": 3,
    "payment.captured": 2,
    "payment.failed": 4,
    "payment.refunded": 3,
    "shipment.dispatched": 4,
    "shipment.delivered": 4,
    "notification.sent": 2,
}


class _WiringCase(unittest.TestCase):
    def setUp(self):
        if EventBus is None:
            self.fail("core.events must export the new API")


class BuildAppTests(_WiringCase):
    def test_each_app_gets_its_own_bus(self):
        reset_default_bus()
        first, second = build_app(), build_app()
        self.assertIsInstance(first.bus, EventBus)
        self.assertIsNot(first.bus, second.bus)
        self.assertIsNot(first.bus, default_bus())
        self.assertEqual(default_bus().handlers(EventType.ORDER_CREATED), ())
        reset_default_bus()

    def test_caller_supplied_bus_is_used(self):
        bus = EventBus()
        app = build_app(bus=bus)
        self.assertIs(app.bus, bus)
        self.assertEqual(len(bus.handlers(EventType.ORDER_CREATED)), SUBSCRIBER_COUNTS["order.created"])
        app2 = build_app(bus)
        self.assertIs(app2.bus, bus)

    def test_services_share_the_app_bus(self):
        app = build_app()
        services = list(app.services)
        self.assertEqual(len(services), 10)
        for service in services:
            self.assertIs(getattr(service, "bus", None), app.bus, type(service).__name__)

    def test_subscriber_counts_match_the_legacy_wiring(self):
        app = build_app()
        counts = {t.value: len(app.bus.handlers(t)) for t in EventType}
        self.assertEqual(counts, SUBSCRIBER_COUNTS)
        self.assertEqual(len(app.plugins), 15)


class IsolationTests(_WiringCase):
    def test_two_apps_do_not_see_each_others_events(self):
        one, two = build_app(), build_app()
        one.services.catalog.add_product("kb-01", "Keyboard", 4_999)
        one.services.inventory.receive("kb-01", 5)
        alice = one.services.customers.register("alice@example.test", "Alice")
        one.services.carts.add_item(alice.id, "kb-01", 1)
        one.services.orders.create_order(alice.id)
        self.assertEqual(one.plugins["metrics"].snapshot(), {"order.created": 1})
        self.assertEqual(two.plugins["metrics"].snapshot(), {})
        self.assertEqual(two.plugins["audit"].entries, [])
        self.assertEqual(two.plugins["analytics"].signups, 0)
        two.bus.publish(Event(EventType.CUSTOMER_REGISTERED, {"customer_id": "cus-9", "email": "x@y.test", "name": "X"}))
        self.assertEqual(two.plugins["analytics"].signups, 1)
        self.assertEqual(one.plugins["analytics"].signups, 1)
        self.assertEqual(two.plugins["search_indexer"].index, {"cus-9": {"name": "X", "email": "x@y.test", "tier": "standard"}})
        self.assertNotIn("cus-9", one.plugins["search_indexer"].index)

    def test_handlers_receive_event_objects(self):
        app = build_app()
        count = app.bus.publish(Event(EventType.INVENTORY_LOW, {"sku": "zz-9", "remaining": 1, "threshold": 3}))
        self.assertEqual(count, SUBSCRIBER_COUNTS["inventory.low"])
        self.assertEqual(app.plugins["stock_guard"].alerts, [("zz-9", 1)])
        self.assertEqual(app.plugins["slack_alerts"].alerts, ["low stock zz-9=1"])
        self.assertEqual(app.services.notifications.outbox, [("ops", app.settings.ops_channel, "Low stock: zz-9 (1 left)")])
        self.assertEqual(app.plugins["ops_dashboard"].notifications, 1)
        self.assertEqual(app.plugins["audit"].names(), ["inventory.low", "notification.sent"])
        self.assertEqual(app.plugins["audit"].entries[0][1], {"sku": "zz-9", "remaining": 1, "threshold": 3})

    def test_synthetic_order_created_reaches_every_subscriber(self):
        app = build_app()
        alice = app.services.customers.register("alice@example.test", "Alice")
        event = Event(EventType.ORDER_CREATED, {"order_id": "ord-77", "customer_id": alice.id, "total_cents": 100, "lines": [("kb-01", 1), ("ms-02", 2)]})
        self.assertEqual(app.bus.publish(event), SUBSCRIBER_COUNTS["order.created"])
        self.assertEqual(app.plugins["metrics"].snapshot(), {"order.created": 1})
        self.assertEqual(app.plugins["analytics"].basket_sizes, [2])
        self.assertEqual(app.plugins["cache_invalidator"].invalidated, [f"orders:{alice.id}"])
        self.assertEqual(app.services.notifications.sent_via("email"), ["Order ord-77 received"])
        self.assertEqual(app.plugins["fraud_check"].flagged, [])

    def test_unsubscribing_a_plugin_handler_takes_effect(self):
        app = build_app()
        handler = app.plugins["metrics"]._on_created
        app.bus.unsubscribe(EventType.ORDER_CREATED, handler)
        self.assertEqual(len(app.bus.handlers(EventType.ORDER_CREATED)), SUBSCRIBER_COUNTS["order.created"] - 1)


if __name__ == "__main__":
    unittest.main()
