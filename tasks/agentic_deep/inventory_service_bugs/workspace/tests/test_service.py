import unittest
from datetime import datetime
from decimal import Decimal

from inventory.config import Settings
from inventory.errors import InsufficientStockError, NotFoundError, ValidationError
from inventory.pricing import DiscountRule
from inventory.repository import InMemoryRepository
from inventory.service import InventoryService
from inventory.utils import UTC


def fixed_clock():
    return datetime(2024, 5, 1, 12, 0, tzinfo=UTC)


class ServiceTests(unittest.TestCase):
    def setUp(self):
        settings = Settings(
            data_path=":memory:",
            page_size=2,
            low_stock_threshold=3,
            tax_rate=Decimal("10"),
            discount_rules=(DiscountRule("bulk", "percent", Decimal("20"), min_quantity=10),),
        )
        self.service = InventoryService(InMemoryRepository(), settings, clock=fixed_clock)
        self.service.add_product("pen-01", "Gel pen", "1.50", category="stationery")
        self.service.add_product("NB-02", "Notebook", "4.25", category="stationery")
        self.service.add_product("MUG-03", "Mug", "7.99", category="kitchen")

    def test_receive_and_ship(self):
        self.service.receive("pen-01", 10)
        self.service.ship("PEN-01", 4)
        self.assertEqual(self.service.stock_level("pen-01"), 6)

    def test_shipping_more_than_on_hand_fails(self):
        self.service.receive("NB-02", 2)
        with self.assertRaises(InsufficientStockError) as ctx:
            self.service.ship("NB-02", 3)
        self.assertEqual(ctx.exception.available, 2)
        self.assertEqual(self.service.stock_level("NB-02"), 2)

    def test_unknown_sku(self):
        with self.assertRaises(NotFoundError):
            self.service.receive("NOPE", 1)

    def test_negative_receipt_is_rejected(self):
        with self.assertRaises(ValidationError):
            self.service.receive("pen-01", 0)

    def test_low_stock(self):
        self.service.receive("pen-01", 10)
        self.service.receive("NB-02", 3)
        rows = self.service.low_stock()
        self.assertEqual([p.sku for p, _ in rows], ["MUG-03", "NB-02"])

    def test_quote_uses_settings(self):
        q = self.service.quote("MUG-03", 10)
        self.assertEqual(q.unit_price, Decimal("6.39"))
        self.assertEqual(q.subtotal, Decimal("63.90"))
        self.assertEqual(q.tax, Decimal("6.39"))
        self.assertEqual(q.total, Decimal("70.29"))

    def test_movements_since_orders_by_time(self):
        self.service.receive("pen-01", 5, at="2024-04-01T00:00:00Z")
        self.service.receive("pen-01", 5, at="2024-04-03T00:00:00Z")
        self.service.ship("pen-01", 1, at="2024-04-02T00:00:00Z")
        rows = self.service.movements_since("2024-04-02T00:00:00Z")
        self.assertEqual([m.quantity for m in rows], [-1, 5])


if __name__ == "__main__":
    unittest.main()
