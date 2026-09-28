"""Settings file loading.

The settings file is a JSON document::

    {
      "data_path": "warehouse.json",
      "page_size": 20,
      "low_stock_threshold": 5,
      "currency": "USD",
      "tax_rate": "8.5",
      "discount_rules": [
        {"name": "bulk", "kind": "percent", "value": "10", "min_quantity": 10}
      ]
    }

Only ``data_path`` is required. Any problem with the file - missing,
unreadable, malformed or semantically invalid - is reported as
:class:`~inventory.errors.ConfigError` so the CLI can print a one-line
message instead of a traceback.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from inventory.errors import ConfigError, InventoryError
from inventory.pricing import DiscountRule

REQUIRED_KEYS = ("data_path",)


@dataclass(frozen=True)
class Settings:
    data_path: str
    page_size: int = 20
    low_stock_threshold: int = 5
    currency: str = "USD"
    tax_rate: Decimal = Decimal(0)
    discount_rules: tuple[DiscountRule, ...] = ()


def load_settings(path: str | Path) -> Settings:
    """Read and validate the settings file at ``path``."""
    file = Path(path)
    try:
        text = file.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"cannot read settings file {file}: {exc.strerror or exc}") from exc
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"settings file {file} is not valid JSON: {exc}") from exc
    return settings_from_dict(raw)


def settings_from_dict(raw: Any) -> Settings:
    if not isinstance(raw, dict):
        raise ConfigError("settings document must be a JSON object")
    missing = [key for key in REQUIRED_KEYS if key not in raw]
    if missing:
        raise ConfigError(f"missing required setting(s): {', '.join(missing)}")

    page_size = _int_setting(raw, "page_size", 20)
    if page_size < 1:
        raise ConfigError("page_size must be >= 1")
    threshold = _int_setting(raw, "low_stock_threshold", 5)
    if threshold < 0:
        raise ConfigError("low_stock_threshold must be >= 0")

    currency = str(raw.get("currency", "USD")).upper()
    if len(currency) != 3 or not currency.isalpha():
        raise ConfigError(f"currency must be a 3-letter code, got {currency!r}")

    try:
        tax_rate = Decimal(str(raw.get("tax_rate", "0")))
    except InvalidOperation as exc:
        raise ConfigError(f"tax_rate is not a number: {raw.get('tax_rate')!r}") from exc
    if tax_rate < 0:
        raise ConfigError("tax_rate must not be negative")

    rules = tuple(_parse_rule(item) for item in raw.get("discount_rules", []))
    return Settings(
        data_path=str(raw["data_path"]),
        page_size=page_size,
        low_stock_threshold=threshold,
        currency=currency,
        tax_rate=tax_rate,
        discount_rules=rules,
    )


def _int_setting(raw: dict[str, Any], key: str, default: int) -> int:
    value = raw.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"{key} must be an integer, got {value!r}")
    return value


def _parse_rule(item: Any) -> DiscountRule:
    if not isinstance(item, dict):
        raise ConfigError("each discount rule must be a JSON object")
    try:
        return DiscountRule(
            name=str(item["name"]),
            kind=str(item["kind"]),
            value=Decimal(str(item["value"])),
            min_quantity=int(item.get("min_quantity", 1)),
            category=item.get("category"),
        )
    except KeyError as exc:
        raise ConfigError(f"discount rule is missing {exc.args[0]!r}") from exc
    except (InvalidOperation, ValueError, InventoryError) as exc:
        raise ConfigError(f"invalid discount rule: {exc}") from exc
