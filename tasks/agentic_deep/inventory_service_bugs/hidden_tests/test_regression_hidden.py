import unittest
from datetime import datetime
from decimal import Decimal

from inventory import reports
from inventory.config import Settings
from inventory.errors import InsufficientStockError, ValidationError
from inventory.pricing import DiscountRule
from inventory.repository import InMemoryRepository
from inventory.service import InventoryService
from inventory.utils import UTC, format_money


class RegressionHiddenTests(unittest.TestCase):
    def setUp(self):
        settings = Settings(
            data_path=":memory:", page_size=10, low_stock_threshold=2, tax_rate=Decimal("5"),
            discount_rules=(DiscountRule("bulk", "percent", Decimal("15"), min_quantity=5),),
        )
        self.service = InventoryService(InMemoryRepository(), settings,
                                        clock=lambda: datetime(2024, 6, 1, tzinfo=UTC))
        self.service.add_product("cup", "Cup", "3.30", category="kitchen")
        self.service.add_product("pot", "Pot", "25", category="kitchen")

    def test_adjust_and_ship(self):
        self.service.receive("cup", 4)
        self.service.adjust("cup", -1, reason="breakage")
        with self.assertRaises(ValidationError):
            self.service.adjust("cup", -5)
        self.service.ship("cup", 3)
        self.assertEqual(self.service.stock_level("CUP"), 0)
        with self.assertRaises(InsufficientStockError):
            self.service.ship("cup", 1)

    def test_naive_datetime_rejected(self):
        with self.assertRaises(ValidationError):
            self.service.receive("cup", 1, at=datetime(2024, 1, 1))

    def test_low_stock_report(self):
        self.service.receive("pot", 5)
        text = reports.low_stock_report(self.service)
        self.assertEqual(text, "Low stock:\n  CUP            0  Cup")
        self.assertEqual(reports.low_stock_report(self.service, threshold=-1),
                         "All products are above the low-stock threshold.")

    def test_stock_report(self):
        self.service.receive("cup", 12)
        self.assertEqual(
            reports.stock_report(self.service),
            "SKU        NAME  ON HAND\nCUP        Cup       12\nPOT        Pot        0",
        )

    def test_quote_report(self):
        text = reports.quote_report(self.service, "cup", 5)
        self.assertIn("unit price:  2.81 USD  [bulk]", text)   # 3.30 * 0.85 = 2.805 -> 2.81
        self.assertIn("subtotal:    14.05 USD", text)
        self.assertIn("tax:         0.70 USD", text)
        self.assertIn("total:       14.75 USD", text)

    def test_format_money(self):
        self.assertEqual(format_money(Decimal("1234.5"), "EUR"), "1,234.50 EUR")


if __name__ == "__main__":
    unittest.main()
