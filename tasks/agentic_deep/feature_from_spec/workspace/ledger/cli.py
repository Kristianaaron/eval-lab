"""Command line interface: ``python -m ledger.cli --file books.json <command>``."""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path
from typing import Sequence, TextIO

from ledger import reports, store
from ledger.book import Ledger
from ledger.errors import LedgerError, ValidationError
from ledger.models import Posting
from ledger.money import format_amount, parse_amount


def parse_date(text: str) -> date:
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise ValidationError(f"invalid date: {text!r} (expected YYYY-MM-DD)") from exc


def parse_posting(text: str) -> Posting:
    """``'1000:-45.50'`` -> Posting."""
    parts = text.split(":")
    if len(parts) != 2:
        raise ValidationError(f"invalid posting {text!r} (expected ACCOUNT:AMOUNT)")
    return Posting(account=parts[0], amount=parse_amount(parts[1]))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ledger", description="Double-entry bookkeeping")
    parser.add_argument("--file", required=True, help="JSON ledger file (created if missing)")
    sub = parser.add_subparsers(dest="command", required=True)

    open_cmd = sub.add_parser("open", help="open an account")
    open_cmd.add_argument("code")
    open_cmd.add_argument("name")
    open_cmd.add_argument("kind", help="asset|liability|equity|income|expense")

    post = sub.add_parser("post", help="record a transaction")
    post.add_argument("date")
    post.add_argument("memo")
    post.add_argument("postings", nargs="+", metavar="ACCOUNT:AMOUNT")

    balance = sub.add_parser("balance", help="print an account balance")
    balance.add_argument("code")
    balance.add_argument("--as-of")

    trial = sub.add_parser("trial-balance", help="print the trial balance")
    trial.add_argument("--as-of")
    return parser


def load_or_create(path: str) -> Ledger:
    if Path(path).exists():
        return store.load(path)
    return Ledger()


def run(args: argparse.Namespace, out: TextIO) -> int:
    ledger = load_or_create(args.file)
    if args.command == "open":
        account = ledger.open_account(args.code, args.name, args.kind)
        store.save(ledger, args.file)
        out.write(f"opened {account.code} {account.name} ({account.kind.value})\n")
    elif args.command == "post":
        postings = [parse_posting(p) for p in args.postings]
        txn = ledger.post(parse_date(args.date), args.memo, postings)
        store.save(ledger, args.file)
        out.write(f"posted transaction {txn.id}\n")
    elif args.command == "balance":
        as_of = parse_date(args.as_of) if args.as_of else None
        out.write(f"{format_amount(ledger.balance(args.code, as_of=as_of))}\n")
    elif args.command == "trial-balance":
        as_of = parse_date(args.as_of) if args.as_of else None
        out.write(reports.trial_balance(ledger, as_of=as_of) + "\n")
    return 0


def main(
    argv: Sequence[str] | None = None, out: TextIO | None = None, err: TextIO | None = None
) -> int:
    out = out or sys.stdout
    err = err or sys.stderr
    args = build_parser().parse_args(argv)
    try:
        return run(args, out)
    except LedgerError as exc:
        err.write(f"error: {exc}\n")
        return 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
