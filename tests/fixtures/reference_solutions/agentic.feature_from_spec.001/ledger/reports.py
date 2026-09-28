"""Plain-text reports."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from ledger.book import Ledger
from ledger.currency import normalise_code
from ledger.errors import ValidationError
from ledger.money import format_amount


def trial_balance(ledger: Ledger, as_of: date | None = None) -> str:
    """One line per account with its balance, then a total line.

    Example::

        Trial balance as of 2024-01-31
        1000  Cash                        954.50
        4000  Sales                    -2,000.00
        Total                                0.00
    """
    heading = "Trial balance" + (f" as of {as_of.isoformat()}" if as_of else "")
    lines = [heading]
    total = Decimal(0)
    for account in ledger.accounts():
        balance = ledger.balance(account.code, as_of=as_of)
        total += balance
        lines.append(f"{account.code:<6}{account.name[:22]:<22}{format_amount(balance):>14}")
    lines.append(f"{'Total':<28}{format_amount(total):>14}")
    return "\n".join(lines)


def statement(
    ledger: Ledger, code: str, start: date, end: date, currency: str | None = None
) -> str:
    """Opening balance, one line per transaction, closing balance."""
    account = ledger.account(code)
    if end < start:
        raise ValidationError("statement period end is before its start")
    target = normalise_code(currency) if currency is not None else ledger.base_currency
    ledger.rates.rate(target)
    opening = ledger.balance(account.code, as_of=start - timedelta(days=1), currency=target)
    lines = [
        f"Statement for {account.code} {account.name}",
        f"Period {start.isoformat()} to {end.isoformat()} ({target})",
        f"{'Opening balance':<50}{format_amount(opening):>12}",
    ]
    running = opening
    for txn in ledger.transactions(account=account.code, start=start, end=end):
        amount = txn.amount_for(account.code, ledger.rates, target)
        running += amount
        lines.append(
            f"{txn.date.isoformat()}  {txn.memo[:26]:<26}"
            f"{format_amount(amount):>12}{format_amount(running):>12}"
        )
    lines.append(f"{'Closing balance':<50}{format_amount(running):>12}")
    return "\n".join(lines)
