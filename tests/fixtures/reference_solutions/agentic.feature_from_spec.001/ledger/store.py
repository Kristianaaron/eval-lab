"""JSON persistence for a :class:`~ledger.book.Ledger`."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from ledger.book import Ledger
from ledger.errors import ValidationError
from ledger.models import AccountKind, Posting, Transaction

FORMAT_VERSION = 2


def to_document(ledger: Ledger) -> dict[str, Any]:
    return {
        "version": FORMAT_VERSION,
        "base_currency": ledger.base_currency,
        "rates": {code: str(rate) for code, rate in ledger.rates.rates().items()},
        "accounts": [
            {"code": a.code, "name": a.name, "kind": a.kind.value} for a in ledger.accounts()
        ],
        "transactions": [
            {
                "id": t.id,
                "date": t.date.isoformat(),
                "memo": t.memo,
                "postings": [
                    {"account": p.account, "amount": str(p.amount), "currency": p.currency}
                    for p in t.postings
                ],
            }
            for t in ledger.transactions()
        ],
    }


def from_document(raw: Any) -> Ledger:
    if not isinstance(raw, dict):
        raise ValidationError("ledger document must be a JSON object")
    ledger = Ledger(raw.get("base_currency", "USD"))
    for code, rate in (raw.get("rates") or {}).items():
        ledger.rates.set_rate(code, rate)
    for item in raw.get("accounts", []):
        ledger.open_account(item["code"], item["name"], AccountKind.parse(item["kind"]))
    for item in raw.get("transactions", []):
        postings = tuple(
            Posting(account=p["account"], amount=Decimal(p["amount"]), currency=p.get("currency"))
            for p in item["postings"]
        )
        ledger.restore_transaction(
            Transaction(
                id=int(item["id"]),
                date=date.fromisoformat(item["date"]),
                memo=item["memo"],
                postings=postings,
            )
        )
    return ledger


def save(ledger: Ledger, path: str | Path) -> None:
    Path(path).write_text(json.dumps(to_document(ledger), indent=2), encoding="utf-8")


def load(path: str | Path) -> Ledger:
    file = Path(path)
    try:
        raw = json.loads(file.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValidationError(f"cannot read {file}: {exc.strerror or exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValidationError(f"{file} is not valid JSON: {exc}") from exc
    return from_document(raw)
