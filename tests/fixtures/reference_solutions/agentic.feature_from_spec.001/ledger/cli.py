"""Command line interface: ``python -m ledger.cli --file books.json <command>``."""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path
from typing import Sequence, TextIO

from ledger import export, reports, store
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
    """``'1000:-45.50'`` or ``'1000:-45.50:EUR'`` -> Posting."""
    parts = text.split(":")
    if len(parts) not in (2, 3):
        raise ValidationError(
            f"invalid posting {text!r} (expected ACCOUNT:AMOUNT or ACCOUNT:AMOUNT:CURRENCY)"
        )
    currency = parts[2] if len(parts) == 3 else None
    return Posting(account=parts[0], amount=parse_amount(parts[1]), currency=currency)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ledger", description="Double-entry bookkeeping")
    parser.add_argument("--file", required=True, help="JSON ledger file (created if missing)")
    parser.add_argument(
        "--base-currency", default="USD", help="base currency for a newly created ledger"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    open_cmd = sub.add_parser("open", help="open an account")
    open_cmd.add_argument("code")
    open_cmd.add_argument("name")
    open_cmd.add_argument("kind", help="asset|liability|equity|income|expense")

    post = sub.add_parser("post", help="record a transaction")
    post.add_argument("date")
    post.add_argument("memo")
    post.add_argument("postings", nargs="+", metavar="ACCOUNT:AMOUNT[:CURRENCY]")

    balance = sub.add_parser("balance", help="print an account balance")
    balance.add_argument("code")
    balance.add_argument("--as-of")
    balance.add_argument("--currency")

    trial = sub.add_parser("trial-balance", help="print the trial balance")
    trial.add_argument("--as-of")

    rate = sub.add_parser("rate", help="set an exchange rate against the base currency")
    rate.add_argument("code")
    rate.add_argument("rate")

    stmt = sub.add_parser("statement", help="print an account statement for a period")
    stmt.add_argument("code")
    stmt.add_argument("start")
    stmt.add_argument("end")
    stmt.add_argument("--currency")

    exp = sub.add_parser("export", help="export postings as CSV")
    exp.add_argument("--start")
    exp.add_argument("--end")
    exp.add_argument("--out")
    return parser


def load_or_create(path: str, base_currency: str = "USD") -> Ledger:
    if Path(path).exists():
        return store.load(path)
    return Ledger(base_currency)


def run(args: argparse.Namespace, out: TextIO) -> int:
    ledger = load_or_create(args.file, args.base_currency)
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
        amount = ledger.balance(args.code, as_of=as_of, currency=args.currency)
        out.write(f"{format_amount(amount)}\n")
    elif args.command == "trial-balance":
        as_of = parse_date(args.as_of) if args.as_of else None
        out.write(reports.trial_balance(ledger, as_of=as_of) + "\n")
    elif args.command == "rate":
        ledger.rates.set_rate(args.code, args.rate)
        store.save(ledger, args.file)
        code = args.code.strip().upper()
        out.write(f"rate {code} = {ledger.rates.rate(code)}\n")
    elif args.command == "statement":
        text = reports.statement(
            ledger, args.code, parse_date(args.start), parse_date(args.end), currency=args.currency
        )
        out.write(text + "\n")
    elif args.command == "export":
        start = parse_date(args.start) if args.start else None
        end = parse_date(args.end) if args.end else None
        if args.out:
            export.write_csv(ledger, args.out, start=start, end=end)
        else:
            out.write(export.export_csv(ledger, start=start, end=end))
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
