import unittest

from inventory.errors import ValidationError
from inventory.utils import paginate


class PaginateTests(unittest.TestCase):
    def setUp(self):
        self.items = ["a", "b", "c", "d", "e"]

    def test_first_page_holds_page_size_items(self):
        page = paginate(self.items, page=1, page_size=2)
        self.assertEqual(page.items, ("a", "b"))
        self.assertEqual(page.total, 5)
        self.assertEqual(page.pages, 3)
        self.assertTrue(page.has_next)
        self.assertFalse(page.has_previous)

    def test_last_page_is_partial(self):
        page = paginate(self.items, page=3, page_size=2)
        self.assertEqual(page.items, ("e",))
        self.assertFalse(page.has_next)

    def test_invalid_page_numbers_are_rejected(self):
        with self.assertRaises(ValidationError):
            paginate(self.items, page=0, page_size=2)
        with self.assertRaises(ValidationError):
            paginate(self.items, page=1, page_size=0)


if __name__ == "__main__":
    unittest.main()
