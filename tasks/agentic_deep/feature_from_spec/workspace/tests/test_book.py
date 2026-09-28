import unittest
from datetime import date
from decimal import Decimal

from ledger.book import Ledger
from ledger.errors import (
    DuplicateAccountError,
    UnbalancedTransactionError,
    UnknownAccountError,
    ValidationError,
)
from ledger.models import AccountKind, Posting


def sample_ledger():
    ledger = Ledger()
    ledger.open_account("1000", "Cash", AccountKind.ASSET)
    ledger.open_account("4000", "Sales", "income")
    ledger.open_account("6000", "Office", AccountKind.EXPENSE)
    ledger.post(date(2024, 1, 5), "Office supplies", [Posting("6000", Decimal("45.50")), Posting("1000", Decimal("-45.50"))])
    ledger.post(date(2024, 1, 20), "Client payment", [Posting("1000", Decimal("2000")), Posting("4000", Decimal("-2000"))])
    ledger.post(date(2024, 1, 2), "Opening float", [Posting("1000", Decimal("1000")), Posting("4000", Decimal("-1000"))])
    return ledger


class LedgerTests(unittest.TestCase):
    def test_balances(self):
        ledger = sample_ledger()
        self.assertEqual(ledger.balance("1000"), Decimal("2954.50"))
        self.assertEqual(ledger.balance("1000", as_of=date(2024, 1, 10)), Decimal("954.50"))
        self.assertEqual(ledger.balance("4000"), Decimal("-3000.00"))

    def test_transactions_are_ordered_by_date_then_id(self):
        ledger = sample_ledger()
        self.assertEqual([t.id for t in ledger.transactions()], [3, 1, 2])
        self.assertEqual([t.id for t in ledger.transactions(account="6000")], [1])
        self.assertEqual([t.id for t in ledger.transactions(start=date(2024, 1, 3), end=date(2024, 1, 19))], [1])

    def test_unbalanced(self):
        ledger = sample_ledger()
        with self.assertRaises(UnbalancedTransactionError) as ctx:
            ledger.post(date(2024, 2, 1), "Oops", [Posting("1000", Decimal("10")), Posting("4000", Decimal("-9"))])
        self.assertEqual(ctx.exception.difference, Decimal("1.00"))

    def test_unknown_and_duplicate_accounts(self):
        ledger = sample_ledger()
        with self.assertRaises(UnknownAccountError):
            ledger.post(date(2024, 2, 1), "x", [Posting("9999", Decimal("1")), Posting("1000", Decimal("-1"))])
        with self.assertRaises(DuplicateAccountError):
            ledger.open_account("1000", "Cash again", "asset")
        with self.assertRaises(UnknownAccountError):
            ledger.balance("9999")

    def test_validation(self):
        ledger = sample_ledger()
        with self.assertRaises(ValidationError):
            ledger.post(date(2024, 2, 1), "", [Posting("1000", Decimal("1")), Posting("4000", Decimal("-1"))])
        with self.assertRaises(ValidationError):
            ledger.post(date(2024, 2, 1), "one leg", [Posting("1000", Decimal("1"))])
        with self.assertRaises(ValidationError):
            Posting("1000", Decimal("0"))
        with self.assertRaises(ValidationError):
            AccountKind.parse("piggybank")


if __name__ == "__main__":
    unittest.main()
