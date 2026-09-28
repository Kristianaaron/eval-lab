"""CSV export of every posting in the ledger."""

from __future__ import annotations

import csv
import io
from datetime import date
from pathlib import Path

from ledger.book import Ledger
from ledger.money import quantize

CSV_HEADER = ["transaction_id", "date", "memo", "account", "amount", "currency"]


def export_csv(ledger: Ledger, start: date | None = None, end: date | None = None) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(CSV_HEADER)
    for txn in ledger.transactions(start=start, end=end):
        for leg in txn.postings:
            writer.writerow(
                [
                    txn.id,
                    txn.date.isoformat(),
                    txn.memo,
                    leg.account,
                    f"{quantize(leg.amount):.2f}",
                    leg.currency or ledger.base_currency,
                ]
            )
    return buffer.getvalue()


def write_csv(
    ledger: Ledger, path: str | Path, start: date | None = None, end: date | None = None
) -> None:
    Path(path).write_text(export_csv(ledger, start=start, end=end), encoding="utf-8")
