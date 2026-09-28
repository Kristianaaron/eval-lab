"""Plain-text reports."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from ledger.book import Ledger
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
