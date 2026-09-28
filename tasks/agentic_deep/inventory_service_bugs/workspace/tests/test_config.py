import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from inventory.config import load_settings, settings_from_dict
from inventory.errors import ConfigError


class SettingsTests(unittest.TestCase):
    def test_full_document(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            path.write_text(json.dumps({
                "data_path": "wh.json",
                "page_size": 5,
                "tax_rate": "8.5",
                "discount_rules": [{"name": "bulk", "kind": "percent", "value": "10", "min_quantity": 10}],
            }))
            settings = load_settings(path)
        self.assertEqual(settings.page_size, 5)
        self.assertEqual(settings.tax_rate, Decimal("8.5"))
        self.assertEqual(settings.discount_rules[0].min_quantity, 10)
        self.assertEqual(settings.currency, "USD")

    def test_missing_required_key(self):
        with self.assertRaises(ConfigError):
            settings_from_dict({"page_size": 3})

    def test_bad_page_size(self):
        with self.assertRaises(ConfigError):
            settings_from_dict({"data_path": "x", "page_size": 0})

    def test_missing_file(self):
        with self.assertRaises(ConfigError):
            load_settings("/nonexistent/settings.json")


if __name__ == "__main__":
    unittest.main()
