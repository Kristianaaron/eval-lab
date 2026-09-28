"""``python -m cli.main <command>``."""

from __future__ import annotations

import argparse
import sys
from typing import Sequence, TextIO

from app import build_app
from cli.commands import events as events_cmd
from cli.commands import orders as orders_cmd
from cli.commands import report as report_cmd
from cli.commands import stock as stock_cmd
from core.errors import AppError

COMMANDS = {
    "demo": orders_cmd.run_demo,
    "stock": stock_cmd.show_stock,
    "report": report_cmd.show_report,
    "events": events_cmd.list_events,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="shop")
    parser.add_argument("command", choices=sorted(COMMANDS))
    return parser


def main(argv: Sequence[str] | None = None, out: TextIO | None = None) -> int:
    out = out or sys.stdout
    args = build_parser().parse_args(argv)
    app = build_app()
    try:
        COMMANDS[args.command](app, out)
    except AppError as exc:
        out.write(f"error: {exc}\n")
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
