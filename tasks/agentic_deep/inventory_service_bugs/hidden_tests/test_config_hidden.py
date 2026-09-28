import io
import json
import tempfile
import unittest
from pathlib import Path

from inventory.cli import main
from inventory.config import load_settings, settings_from_dict
from inventory.errors import ConfigError, InventoryError


class ConfigHiddenTests(unittest.TestCase):
    def _write(self, tmp, text):
        path = Path(tmp) / "settings.json"
        path.write_text(text, encoding="utf-8")
        return path

    def test_invalid_json_raises_config_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(tmp, '{"data_path": "x",')
            with self.assertRaises(ConfigError) as ctx:
                load_settings(path)
        self.assertIsInstance(ctx.exception, InventoryError)
        self.assertIn("not valid JSON", str(ctx.exception))

    def test_invalid_json_does_not_leak_value_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(tmp, "not json at all")
            try:
                load_settings(path)
            except InventoryError:
                pass
            else:
                self.fail("load_settings should raise")

    def test_non_object_document(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(tmp, "[1, 2, 3]")
            with self.assertRaises(ConfigError):
                load_settings(path)

    def test_directory_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ConfigError):
                load_settings(tmp)

    def test_invalid_rule_is_config_error(self):
        with self.assertRaises(ConfigError):
            settings_from_dict({"data_path": "x", "discount_rules": [{"name": "a", "kind": "percent"}]})
        with self.assertRaises(ConfigError):
            settings_from_dict({"data_path": "x", "discount_rules": [{"name": "a", "kind": "percent", "value": "150"}]})

    def test_cli_reports_broken_settings_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(tmp, "{oops")
            out, err = io.StringIO(), io.StringIO()
            code = main(["--config", str(path), "list"], out=out, err=err)
        self.assertEqual(code, 2)
        self.assertTrue(err.getvalue().startswith("error: "), err.getvalue())
        self.assertIn("not valid JSON", err.getvalue())
        self.assertEqual(out.getvalue(), "")

    def test_cli_round_trip_with_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "wh.json"
            path = self._write(tmp, json.dumps({"data_path": str(data), "page_size": 1, "tax_rate": "10"}))
            cfg = ["--config", str(path)]
            self.assertEqual(main(cfg + ["add", "a1", "Alpha", "10.70"], out=io.StringIO()), 0)
            self.assertEqual(main(cfg + ["add", "b2", "Beta", "3"], out=io.StringIO()), 0)
            self.assertEqual(main(cfg + ["receive", "a1", "5", "--at", "2024-01-01T10:00:00+02:00"], out=io.StringIO()), 0)
            out = io.StringIO()
            self.assertEqual(main(cfg + ["list", "--page", "2"], out=out), 0)
            self.assertEqual(out.getvalue(), "B2         Beta\npage 2 of 2 (2 products)\n")
            out = io.StringIO()
            self.assertEqual(main(cfg + ["quote", "A1", "2"], out=out), 0)
            self.assertIn("total:       23.54 USD", out.getvalue())
            stored = json.loads(data.read_text())
            self.assertEqual(stored["movements"][0]["recorded_at"], "2024-01-01T08:00:00Z")
            err = io.StringIO()
            self.assertEqual(main(cfg + ["ship", "A1", "9"], out=io.StringIO(), err=err), 2)
            self.assertEqual(err.getvalue(), "error: cannot ship 9 x A1: only 5 on hand\n")


if __name__ == "__main__":
    unittest.main()
