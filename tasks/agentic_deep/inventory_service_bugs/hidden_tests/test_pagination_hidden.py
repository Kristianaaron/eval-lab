import unittest

from inventory.errors import ValidationError
from inventory.repository import InMemoryRepository
from inventory.service import InventoryService
from inventory.utils import paginate


class PaginateHiddenTests(unittest.TestCase):
    def setUp(self):
        self.items = list(range(1, 11))  # 1..10

    def test_every_page_has_page_size_items(self):
        for page in (1, 2, 3):
            self.assertEqual(len(paginate(self.items, page, 3).items), 3, page)
        self.assertEqual(paginate(self.items, 4, 3).items, (10,))

    def test_pages_are_contiguous_and_cover_everything(self):
        seen = []
        for page in range(1, 5):
            seen.extend(paginate(self.items, page, 3).items)
        self.assertEqual(seen, self.items)

    def test_page_size_one(self):
        page = paginate(self.items, 7, 1)
        self.assertEqual(page.items, (7,))
        self.assertEqual(page.pages, 10)
        self.assertTrue(page.has_next)
        self.assertTrue(page.has_previous)

    def test_exact_multiple(self):
        page = paginate(self.items, 2, 5)
        self.assertEqual(page.items, (6, 7, 8, 9, 10))
        self.assertEqual(page.pages, 2)
        self.assertFalse(page.has_next)

    def test_page_past_the_end_is_empty(self):
        page = paginate(self.items, 9, 4)
        self.assertEqual(page.items, ())
        self.assertEqual(page.total, 10)
        self.assertFalse(page.has_next)

    def test_empty_listing(self):
        page = paginate([], 1, 20)
        self.assertEqual(page.items, ())
        self.assertEqual(page.pages, 1)
        self.assertFalse(page.has_next)

    def test_validation(self):
        with self.assertRaises(ValidationError):
            paginate(self.items, 0, 3)
        with self.assertRaises(ValidationError):
            paginate(self.items, 1, -1)

    def test_service_listing_uses_settings_page_size(self):
        from inventory.config import Settings

        service = InventoryService(InMemoryRepository(), Settings(data_path="x", page_size=2))
        for i in range(5):
            service.add_product(f"S{i}", f"Item {i}", "1.00", category="a" if i < 3 else "b")
        first = service.list_products()
        self.assertEqual([p.sku for p in first.items], ["S0", "S1"])
        self.assertEqual(first.pages, 3)
        third = service.list_products(page=3)
        self.assertEqual([p.sku for p in third.items], ["S4"])
        filtered = service.list_products(page=1, page_size=10, category="b")
        self.assertEqual([p.sku for p in filtered.items], ["S3", "S4"])


if __name__ == "__main__":
    unittest.main()
