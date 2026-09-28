import dataclasses
import unittest

try:
    from core.events import Event, EventBus, EventType, default_bus, reset_default_bus
except ImportError:  # pragma: no cover - the migration has not happened yet
    Event = EventBus = EventType = default_bus = reset_default_bus = None

EXPECTED = [
    ("CUSTOMER_REGISTERED", "customer.registered"),
    ("CUSTOMER_UPGRADED", "customer.upgraded"),
    ("CART_ITEM_ADDED", "cart.item_added"),
    ("ORDER_CREATED", "order.created"),
    ("ORDER_PAID", "order.paid"),
    ("ORDER_CANCELLED", "order.cancelled"),
    ("ORDER_SHIPPED", "order.shipped"),
    ("INVENTORY_RESERVED", "inventory.reserved"),
    ("INVENTORY_RELEASED", "inventory.released"),
    ("INVENTORY_LOW", "inventory.low"),
    ("PAYMENT_CAPTURED", "payment.captured"),
    ("PAYMENT_FAILED", "payment.failed"),
    ("PAYMENT_REFUNDED", "payment.refunded"),
    ("SHIPMENT_DISPATCHED", "shipment.dispatched"),
    ("SHIPMENT_DELIVERED", "shipment.delivered"),
    ("NOTIFICATION_SENT", "notification.sent"),
]


class _ApiCase(unittest.TestCase):
    def setUp(self):
        if EventBus is None:
            self.fail("core.events must export Event, EventBus, EventType, default_bus, reset_default_bus")


class EventTypeTests(_ApiCase):
    def test_members_values_and_order(self):
        self.assertEqual([(m.name, m.value) for m in EventType], EXPECTED)
        self.assertEqual(len(EventType), 16)
        self.assertIs(EventType("order.paid"), EventType.ORDER_PAID)


class EventTests(_ApiCase):
    def test_defaults_and_immutability(self):
        event = Event(EventType.ORDER_PAID)
        self.assertEqual(dict(event.payload), {})
        self.assertTrue(dataclasses.is_dataclass(event))
        with self.assertRaises(AttributeError):
            event.type = EventType.ORDER_CREATED
        event = Event(EventType.ORDER_PAID, {"order_id": "ord-1"})
        self.assertEqual(event.payload["order_id"], "ord-1")

    def test_type_must_be_event_type(self):
        with self.assertRaises(TypeError):
            Event("order.paid", {})


class EventBusTests(_ApiCase):
    def setUp(self):
        super().setUp()
        self.bus = EventBus()
        self.calls = []

    def _handler(self, tag):
        def handle(event):
            self.calls.append((tag, event))

        return handle

    def test_publish_calls_handlers_in_order_and_returns_count(self):
        first, second = self._handler("first"), self._handler("second")
        self.bus.subscribe(EventType.ORDER_PAID, first)
        self.bus.subscribe(EventType.ORDER_PAID, second)
        event = Event(EventType.ORDER_PAID, {"order_id": "ord-1"})
        self.assertEqual(self.bus.publish(event), 2)
        self.assertEqual([tag for tag, _ in self.calls], ["first", "second"])
        self.assertIs(self.calls[0][1], event)
        self.assertEqual(self.bus.publish(Event(EventType.ORDER_CREATED)), 0)
        self.assertEqual(self.bus.handlers(EventType.ORDER_PAID), (first, second))
        self.assertEqual(self.bus.handlers(EventType.ORDER_CREATED), ())

    def test_duplicate_subscription_and_unsubscribe(self):
        handler = self._handler("h")
        self.bus.subscribe(EventType.ORDER_PAID, handler)
        self.bus.subscribe(EventType.ORDER_PAID, handler)
        self.assertEqual(self.bus.publish(Event(EventType.ORDER_PAID)), 1)
        self.bus.unsubscribe(EventType.ORDER_PAID, handler)
        self.bus.unsubscribe(EventType.ORDER_PAID, handler)  # no-op
        self.bus.unsubscribe(EventType.ORDER_CREATED, handler)  # never subscribed: no-op
        self.assertEqual(self.bus.publish(Event(EventType.ORDER_PAID)), 0)

    def test_type_errors(self):
        handler = self._handler("h")
        with self.assertRaises(TypeError):
            self.bus.subscribe("order.paid", handler)
        with self.assertRaises(TypeError):
            self.bus.unsubscribe("order.paid", handler)
        with self.assertRaises(TypeError):
            self.bus.handlers("order.paid")
        with self.assertRaises(TypeError):
            self.bus.publish({"type": "order.paid", "payload": {}})
        with self.assertRaises(TypeError):
            self.bus.publish("order.paid")

    def test_publish_iterates_over_a_snapshot(self):
        late = self._handler("late")

        def subscribe_late(event):
            self.calls.append(("early", event))
            self.bus.subscribe(EventType.ORDER_PAID, late)

        self.bus.subscribe(EventType.ORDER_PAID, subscribe_late)
        self.assertEqual(self.bus.publish(Event(EventType.ORDER_PAID)), 1)
        self.assertEqual([tag for tag, _ in self.calls], ["early"])
        self.assertEqual(self.bus.publish(Event(EventType.ORDER_PAID)), 2)

    def test_buses_are_independent_and_clear(self):
        other = EventBus()
        self.bus.subscribe(EventType.ORDER_PAID, self._handler("a"))
        self.assertEqual(other.publish(Event(EventType.ORDER_PAID)), 0)
        self.assertEqual(other.handlers(EventType.ORDER_PAID), ())
        self.bus.clear()
        self.assertEqual(self.bus.publish(Event(EventType.ORDER_PAID)), 0)


class DefaultBusTests(_ApiCase):
    def test_singleton_and_reset(self):
        reset_default_bus()
        first = default_bus()
        self.assertIsInstance(first, EventBus)
        self.assertIs(default_bus(), first)
        reset_default_bus()
        second = default_bus()
        self.assertIsNot(second, first)
        reset_default_bus()


if __name__ == "__main__":
    unittest.main()
