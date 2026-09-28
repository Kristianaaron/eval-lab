import json
import tempfile
import unittest
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from inventory.errors import NotFoundError, ValidationError
from inventory.models import Product, StockMovement
from inventory.repository import InMemoryRepository, JsonFileRepository
from inventory.utils import UTC


class InMemoryRepositoryTests(unittest.TestCase):
    def test_duplicate_sku_rejected(self):
        repo = InMemoryRepository()
        repo.add_product(Product("A1", "Thing", Decimal("1")))
        with self.assertRaises(ValidationError):
            repo.add_product(Product("a1", "Other", Decimal("2")))

    def test_movement_for_unknown_product(self):
        repo = InMemoryRepository()
        with self.assertRaises(NotFoundError):
            repo.record_movement(StockMovement("A1", 1, datetime(2024, 1, 1, tzinfo=UTC)))

    def test_stock_levels(self):
        repo = InMemoryRepository([Product("A1", "Thing", Decimal("1")), Product("B2", "Other", 2)])
        repo.record_movement(StockMovement("A1", 5, datetime(2024, 1, 1, tzinfo=UTC)))
        repo.record_movement(StockMovement("A1", -2, datetime(2024, 1, 2, tzinfo=UTC)))
        self.assertEqual(repo.stock_levels(), {"A1": 3, "B2": 0})


class JsonFileRepositoryTests(unittest.TestCase):
    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "store.json"
            repo = JsonFileRepository(path)
            repo.add_product(Product("A1", "Thing", Decimal("1.25"), tags=("x",)))
            repo.record_movement(
                StockMovement("A1", 4, datetime(2024, 1, 1, 9, tzinfo=UTC), reason="r", reference="PO-1")
            )
            repo.save()
            document = json.loads(path.read_text())
            self.assertEqual(document["movements"][0]["recorded_at"], "2024-01-01T09:00:00Z")

            reloaded = JsonFileRepository(path)
            self.assertEqual(reloaded.get_product("A1").unit_price, Decimal("1.25"))
            self.assertEqual(reloaded.stock_level("A1"), 4)
            self.assertEqual(reloaded.movements("A1")[0].reference, "PO-1")


if __name__ == "__main__":
    unittest.main()
