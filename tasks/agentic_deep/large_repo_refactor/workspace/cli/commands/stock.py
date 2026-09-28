"""``shop stock``: on-hand quantities."""

from __future__ import annotations

from typing import TextIO


def show_stock(app, out: TextIO) -> None:
    inventory = app.services.inventory
    if not inventory.stock:
        out.write("(no stock)\n")
        return
    for sku in sorted(inventory.stock):
        out.write(f"{sku:<8}{inventory.stock[sku]:>6}\n")
