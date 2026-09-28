"""Value objects: accounts, postings and transactions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum

from ledger.errors import ValidationError
from ledger.money import quantize


class AccountKind(str, Enum):
    ASSET = "asset"
    LIABILITY = "liability"
    EQUITY = "equity"
    INCOME = "income"
    EXPENSE = "expense"

    @classmethod
    def parse(cls, value: str) -> AccountKind:
        try:
            return cls(value.strip().lower())
        except ValueError as exc:
            valid = ", ".join(kind.value for kind in cls)
            raise ValidationError(f"unknown account kind {value!r} (expected one of {valid})") from exc


@dataclass(frozen=True)
class Account:
    code: str
    name: str
    kind: AccountKind

    def __post_init__(self) -> None:
        if not self.code.strip():
            raise ValidationError("account code must not be empty")
        if not self.name.strip():
            raise ValidationError("account name must not be empty")
        object.__setattr__(self, "code", self.code.strip())
        object.__setattr__(self, "name", self.name.strip())


@dataclass(frozen=True)
class Posting:
    """One leg of a transaction. Positive amounts are debits, negative credits."""

    account: str
    amount: Decimal

    def __post_init__(self) -> None:
        object.__setattr__(self, "account", self.account.strip())
        object.__setattr__(self, "amount", quantize(self.amount))
        if self.amount == 0:
            raise ValidationError("posting amount must not be zero")


@dataclass(frozen=True)
class Transaction:
    id: int
    date: date
    memo: str
    postings: tuple[Posting, ...]

    def touches(self, account: str) -> bool:
        return any(p.account == account for p in self.postings)

    def postings_for(self, account: str) -> tuple[Posting, ...]:
        return tuple(p for p in self.postings if p.account == account)
