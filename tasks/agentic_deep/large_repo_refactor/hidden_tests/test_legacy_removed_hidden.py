import ast
import importlib
import pkgutil
import unittest
from pathlib import Path

import app as app_module
import core.constants
import core.events

ROOT = Path(app_module.__file__).resolve().parent
PACKAGES = ("core", "services", "plugins", "cli")
LEGACY_NAMES = {"emit", "on", "off", "handler_count", "reset", "_HANDLERS"}
ALLOWED_EVENT_IMPORTS = {"Event", "EventType", "EventBus", "Handler", "default_bus", "reset_default_bus"}


def source_files():
    files = [ROOT / "app.py"]
    for package in PACKAGES:
        files.extend(sorted((ROOT / package).rglob("*.py")))
    return files


class LegacyApiRemovedTests(unittest.TestCase):
    def test_core_events_has_no_legacy_names(self):
        for name in LEGACY_NAMES:
            self.assertFalse(hasattr(core.events, name), f"core.events.{name} still exists")
        for name in ("Event", "EventBus", "EventType", "default_bus", "reset_default_bus"):
            self.assertTrue(hasattr(core.events, name), f"core.events.{name} is missing")

    def test_core_constants_has_no_event_names(self):
        leftovers = [n for n in dir(core.constants) if n.startswith("EVENT_") or n == "ALL_EVENTS"]
        self.assertEqual(leftovers, [])
        for name in ("DEFAULT_CURRENCY", "MAX_LINES_PER_ORDER", "SUPPORTED_CARRIERS", "NOTIFICATION_CHANNELS"):
            self.assertTrue(hasattr(core.constants, name), f"core.constants.{name} was removed")

    def test_no_module_imports_or_calls_the_legacy_api(self):
        offenders = []
        for path in source_files():
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            aliases = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    if node.module == "core.events":
                        bad = {a.name for a in node.names} - ALLOWED_EVENT_IMPORTS
                        if bad:
                            offenders.append(f"{path.relative_to(ROOT)}: imports {sorted(bad)} from core.events")
                    if node.module == "core.constants":
                        bad = {a.name for a in node.names if a.name.startswith("EVENT_") or a.name == "ALL_EVENTS"}
                        if bad:
                            offenders.append(f"{path.relative_to(ROOT)}: imports {sorted(bad)} from core.constants")
                    if node.module == "core" and any(a.name == "events" for a in node.names):
                        aliases.add(next(a.asname or a.name for a in node.names if a.name == "events"))
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name == "core.events":
                            aliases.add(alias.asname or "core.events")
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                if isinstance(func, ast.Name) and func.id in LEGACY_NAMES - {"reset"}:
                    offenders.append(f"{path.relative_to(ROOT)}:{node.lineno}: calls {func.id}()")
                if isinstance(func, ast.Attribute) and func.attr in LEGACY_NAMES:
                    owner = ast.unparse(func.value)
                    if owner in aliases or owner in ("events", "ev", "core.events"):
                        offenders.append(f"{path.relative_to(ROOT)}:{node.lineno}: calls {owner}.{func.attr}()")
        self.assertEqual(offenders, [])

    def test_every_module_imports(self):
        failures = []
        for package in PACKAGES:
            pkg = importlib.import_module(package)
            for info in pkgutil.walk_packages(pkg.__path__, prefix=package + "."):
                try:
                    importlib.import_module(info.name)
                except Exception as exc:  # noqa: BLE001
                    failures.append(f"{info.name}: {exc!r}")
        self.assertEqual(failures, [])
        self.assertGreaterEqual(len(list(source_files())), 40)

    def test_plugin_registry_is_intact(self):
        from plugins import PLUGIN_MODULES

        self.assertEqual(len(PLUGIN_MODULES), 15)
        for name in PLUGIN_MODULES:
            module = importlib.import_module(name)
            self.assertTrue(callable(getattr(module, "register", None)), name)


if __name__ == "__main__":
    unittest.main()
