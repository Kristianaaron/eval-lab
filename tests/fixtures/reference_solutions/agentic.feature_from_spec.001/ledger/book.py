"""The Ledger: accounts, transactions, exchange rates and balances."""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal
from typing import Iterable

from ledger.currency import RateTable, normalise_code
from ledger.errors import (
    DuplicateAccountError,
    UnbalancedTransactionError,
    UnknownAccountError,
    ValidationError,
)
from ledger.models import Account, AccountKind, Posting, Transaction


class Ledger:
    def __init__(self, base_currency: str = "USD") -> None:
        self.base_currency = normalise_code(base_currency)
        self.rates = RateTable(self.base_currency)
        self._accounts: dict[str, Account] = {}
        self._transactions: list[Transaction] = []
        self._next_id = 1

    # -- accounts -----------------------------------------------------------
    def open_account(self, code: str, name: str, kind: AccountKind | str) -> Account:
        if isinstance(kind, str):
            kind = AccountKind.parse(kind)
        account = Account(code=code, name=name, kind=kind)
        if account.code in self._accounts:
            raise DuplicateAccountError(account.code)
        self._accounts[account.code] = account
        return account

    def account(self, code: str) -> Account:
        try:
            return self._accounts[code.strip()]
        except KeyError:
            raise UnknownAccountError(code.strip()) from None

    def accounts(self) -> list[Account]:
        return sorted(self._accounts.values(), key=lambda a: a.code)

    # -- transactions -------------------------------------------------------
    def post(self, when: date, memo: str, postings: Iterable[Posting]) -> Transaction:
        legs = tuple(
            leg if leg.currency is not None else replace(leg, currency=self.base_currency)
            for leg in postings
        )
        if not memo or not memo.strip():
            raise ValidationError("memo must not be empty")
        if len(legs) < 2:
            raise ValidationError("a transaction needs at least two postings")
        for leg in legs:
            if leg.account not in self._accounts:
                raise UnknownAccountError(leg.account)
        difference = Decimal(0)
        for leg in legs:
            difference += self.rates.convert(leg.amount, leg.currency, self.base_currency)
        if difference != 0:
            raise UnbalancedTransactionError(difference)
        txn = Transaction(id=self._next_id, date=when, memo=memo.strip(), postings=legs)
        self._next_id += 1
        self._transactions.append(txn)
        return txn

    def transactions(
        self,
        account: str | None = None,
        start: date | None = None,
        end: date | None = None,
    ) -> list[Transaction]:
        """Transactions ordered by (date, id), optionally filtered."""
        rows = self._transactions
        if account is not None:
            self.account(account)
            rows = [t for t in rows if t.touches(account)]
        if start is not None:
            rows = [t for t in rows if t.date >= start]
        if end is not None:
            rows = [t for t in rows if t.date <= end]
        return sorted(rows, key=lambda t: (t.date, t.id))

    def balance(self, code: str, as_of: date | None = None, currency: str | None = None) -> Decimal:
        """Signed balance of ``code`` up to ``as_of``, expressed in ``currency``."""
        account = self.account(code)
        target = normalise_code(currency) if currency is not None else self.base_currency
        self.rates.rate(target)  # fail fast on an unknown currency, even with no postings
        total = Decimal(0)
        for txn in self._transactions:
            if as_of is not None and txn.date > as_of:
                continue
            for leg in txn.postings_for(account.code):
                total += self.rates.convert(leg.amount, leg.currency or self.base_currency, target)
        return total

    def restore_transaction(self, txn: Transaction) -> None:
        """Re-insert a persisted transaction, keeping ids unique (used by the store)."""
        for leg in txn.postings:
            if leg.account not in self._accounts:
                raise UnknownAccountError(leg.account)
        if any(t.id == txn.id for t in self._transactions):
            raise ValidationError(f"duplicate transaction id: {txn.id}")
        legs = tuple(
            leg if leg.currency is not None else replace(leg, currency=self.base_currency)
            for leg in txn.postings
        )
        self._transactions.append(replace(txn, postings=legs))
        self._next_id = max(self._next_id, txn.id + 1)
