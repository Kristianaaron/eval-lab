"""The Ledger: accounts, transactions and balances."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Iterable

from ledger.errors import (
    DuplicateAccountError,
    UnbalancedTransactionError,
    UnknownAccountError,
    ValidationError,
)
from ledger.models import Account, AccountKind, Posting, Transaction


class Ledger:
    def __init__(self) -> None:
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
        legs = tuple(postings)
        if not memo or not memo.strip():
            raise ValidationError("memo must not be empty")
        if len(legs) < 2:
            raise ValidationError("a transaction needs at least two postings")
        for leg in legs:
            if leg.account not in self._accounts:
                raise UnknownAccountError(leg.account)
        difference = sum((leg.amount for leg in legs), Decimal(0))
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

    def balance(self, code: str, as_of: date | None = None) -> Decimal:
        """Signed balance of ``code`` including postings dated up to ``as_of``."""
        account = self.account(code)
        total = Decimal(0)
        for txn in self._transactions:
            if as_of is not None and txn.date > as_of:
                continue
            for leg in txn.postings_for(account.code):
                total += leg.amount
        return total

    def restore_transaction(self, txn: Transaction) -> None:
        """Re-insert a persisted transaction, keeping ids unique (used by the store)."""
        for leg in txn.postings:
            if leg.account not in self._accounts:
                raise UnknownAccountError(leg.account)
        if any(t.id == txn.id for t in self._transactions):
            raise ValidationError(f"duplicate transaction id: {txn.id}")
        self._transactions.append(txn)
        self._next_id = max(self._next_id, txn.id + 1)
