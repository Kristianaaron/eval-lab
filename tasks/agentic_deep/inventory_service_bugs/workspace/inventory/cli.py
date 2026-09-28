"""Command line front-end: ``python -m inventory.cli --config settings.json list``."""

from __future__ import annotations

import argparse
import sys
from typing import Sequence, TextIO

from inventory import reports
from inventory.config import Settings, load_settings
from inventory.errors import InventoryError
from inventory.repository import JsonFileRepository
from inventory.service import InventoryService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="inventory", description="Warehouse inventory tool")
    parser.add_argument("--config", help="path to the JSON settings file")
    sub = parser.add_subparsers(dest="command", required=True)

    add = sub.add_parser("add", help="register a product")
    add.add_argument("sku")
    add.add_argument("name")
    add.add_argument("price")
    add.add_argument("--category", default="general")

    receive = sub.add_parser("receive", help="record a stock receipt")
    receive.add_argument("sku")
    receive.add_argument("quantity", type=int)
    receive.add_argument("--at", help="ISO-8601 timestamp (default: now)")
    receive.add_argument("--reference")

    ship = sub.add_parser("ship", help="record a shipment")
    ship.add_argument("sku")
    ship.add_argument("quantity", type=int)
    ship.add_argument("--at")
    ship.add_argument("--reference")

    listing = sub.add_parser("list", help="list products, one page at a time")
    listing.add_argument("--page", type=int, default=1)
    listing.add_argument("--page-size", type=int)
    listing.add_argument("--category")

    quote = sub.add_parser("quote", help="price a quantity of a product")
    quote.add_argument("sku")
    quote.add_argument("quantity", type=int)

    low = sub.add_parser("low-stock", help="products at or below the threshold")
    low.add_argument("--threshold", type=int)

    sub.add_parser("stock", help="on-hand quantities for every product")
    return parser


def _build_service(config_path: str | None) -> InventoryService:
    if config_path is None:
        # No settings file: work against a throw-away in-memory store.
        return InventoryService()
    settings: Settings = load_settings(config_path)
    return InventoryService(JsonFileRepository(settings.data_path), settings)


def _persist(service: InventoryService) -> None:
    repo = service.repo
    if isinstance(repo, JsonFileRepository):
        repo.save()


def run(args: argparse.Namespace, out: TextIO) -> int:
    service = _build_service(args.config)
    if args.command == "add":
        product = service.add_product(args.sku, args.name, args.price, category=args.category)
        _persist(service)
        out.write(f"added {product.sku}\n")
    elif args.command == "receive":
        movement = service.receive(args.sku, args.quantity, at=args.at, reference=args.reference)
        _persist(service)
        out.write(f"received {movement.quantity} x {movement.sku}\n")
    elif args.command == "ship":
        movement = service.ship(args.sku, args.quantity, at=args.at, reference=args.reference)
        _persist(service)
        out.write(f"shipped {-movement.quantity} x {movement.sku}\n")
    elif args.command == "list":
        page = service.list_products(args.page, args.page_size, category=args.category)
        for product in page.items:
            out.write(f"{product.sku:<10} {product.name}\n")
        out.write(f"page {page.page} of {page.pages} ({page.total} products)\n")
    elif args.command == "quote":
        out.write(reports.quote_report(service, args.sku, args.quantity) + "\n")
    elif args.command == "low-stock":
        out.write(reports.low_stock_report(service, args.threshold) + "\n")
    elif args.command == "stock":
        out.write(reports.stock_report(service) + "\n")
    return 0


def main(argv: Sequence[str] | None = None, out: TextIO | None = None, err: TextIO | None = None) -> int:
    out = out or sys.stdout
    err = err or sys.stderr
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return run(args, out)
    except InventoryError as exc:
        err.write(f"error: {exc}\n")
        return 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
