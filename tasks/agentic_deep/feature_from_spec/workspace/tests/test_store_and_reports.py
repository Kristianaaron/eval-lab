import json
import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

from ledger import reports, store
from ledger.errors import ValidationError
from ledger.models import Posting
from tests.test_book import sample_ledger


class StoreTests(unittest.TestCase):
    def test_round_trip(self):
        ledger = sample_ledger()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "books.json"
            store.save(ledger, path)
            raw = json.loads(path.read_text())
            first = raw["transactions"][0]["postings"][0]
            self.assertEqual((first["account"], first["amount"]), ("1000", "1000.00"))
            reloaded = store.load(path)
        self.assertEqual(reloaded.balance("1000"), Decimal("2954.50"))
        self.assertEqual([t.id for t in reloaded.transactions()], [3, 1, 2])
        self.assertEqual(reloaded.account("4000").kind.value, "income")
        # ids keep counting after the highest persisted id
        txn = reloaded.post(
            date(2024, 3, 1), "More", [Posting("1000", Decimal("1")), Posting("4000", Decimal("-1"))]
        )
        self.assertEqual(txn.id, 4)

    def test_load_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "books.json"
            path.write_text("{")
            with self.assertRaises(ValidationError):
                store.load(path)
            with self.assertRaises(ValidationError):
                store.load(Path(tmp) / "missing.json")


class TrialBalanceTests(unittest.TestCase):
    def test_format(self):
        text = reports.trial_balance(sample_ledger(), as_of=date(2024, 1, 31))
        self.assertEqual(text.splitlines(), [
            "Trial balance as of 2024-01-31",
            "1000  Cash                        2,954.50",
            "4000  Sales                      -3,000.00",
            "6000  Office                         45.50",
            "Total                                 0.00",
        ])


if __name__ == "__main__":
    unittest.main()
