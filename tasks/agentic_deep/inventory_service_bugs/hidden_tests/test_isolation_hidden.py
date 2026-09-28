import io
import tempfile
import unittest
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from inventory.cli import main
from inventory.errors import NotFoundError
from inventory.models import Product, StockMovement
from inventory.repository import InMemoryRepository, JsonFileRepository
from inventory.service import InventoryService
from inventory.utils import UTC


class ServiceIsolationHiddenTests(unittest.TestCase):
    def test_default_services_do_not_share_state(self):
        warehouse_a = InventoryService()
        warehouse_b = InventoryService()
        warehouse_a.add_product("A1", "Alpha", "1.00")
        warehouse_a.receive("A1", 7)
        self.assertEqual(warehouse_a.stock_level("A1"), 7)
        with self.assertRaises(NotFoundError):
            warehouse_b.stock_level("A1")
        self.assertEqual(warehouse_b.list_products().total, 0)
        self.assertIsNot(warehouse_a.repo, warehouse_b.repo)

    def test_default_service_starts_empty_every_time(self):
        first = InventoryService()
        first.add_product("Z9", "Zed", "2")
        self.assertEqual(InventoryService().repo.list_products(), [])

    def test_explicit_repo_is_used(self):
        repo = InMemoryRepository([Product("A1", "Alpha", Decimal("1"))])
        service = InventoryService(repo)
        self.assertIs(service.repo, repo)
        self.assertEqual(service.stock_level("A1"), 0)

    def test_repositories_do_not_share_movements(self):
        a = InMemoryRepository([Product("A1", "Alpha", Decimal("1"))])
        b = InMemoryRepository([Product("A1", "Alpha", Decimal("1"))])
        a.record_movement(StockMovement("A1", 3, datetime(2024, 1, 1, tzinfo=UTC)))
        self.assertEqual(b.movements(), [])
        self.assertEqual(b.stock_level("A1"), 0)

    def test_json_repositories_do_not_share_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = JsonFileRepository(Path(tmp) / "a.json")
            b = JsonFileRepository(Path(tmp) / "b.json")
            a.add_product(Product("A1", "Alpha", Decimal("1")))
            a.record_movement(StockMovement("A1", 3, datetime(2024, 1, 1, tzinfo=UTC)))
            b.save()
            self.assertEqual(JsonFileRepository(Path(tmp) / "b.json").list_products(), [])


class CliIsolationHiddenTests(unittest.TestCase):
    def test_each_invocation_without_config_starts_empty(self):
        out = io.StringIO()
        self.assertEqual(main(["add", "K1", "Kettle", "20"], out=out, err=io.StringIO()), 0)
        out = io.StringIO()
        self.assertEqual(main(["list"], out=out, err=io.StringIO()), 0)
        self.assertEqual(out.getvalue(), "page 1 of 1 (0 products)\n")


if __name__ == "__main__":
    unittest.main()
