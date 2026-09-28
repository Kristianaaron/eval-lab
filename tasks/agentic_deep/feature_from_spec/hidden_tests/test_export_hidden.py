import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

from ledger.book import Ledger
from ledger.models import Posting

try:
    from ledger.export import CSV_HEADER, export_csv, write_csv
except ImportError:  # pragma: no cover
    CSV_HEADER = export_csv = write_csv = None


def sample():
    ledger = Ledger()
    ledger.rates.set_rate("EUR", "1.08")
    ledger.open_account("1000", "Cash", "asset")
    ledger.open_account("4000", "Sales", "income")
    ledger.post(date(2024, 1, 20), "Client payment", [Posting("1000", Decimal("2000")), Posting("4000", Decimal("-2000"))])
    ledger.post(date(2024, 1, 5), 'Paper, "premium" grade', [Posting("4000", Decimal("45.5")), Posting("1000", Decimal("-45.50"))])
    ledger.post(date(2024, 1, 25), "EUR sale", [Posting("1000", Decimal("100"), "EUR"), Posting("4000", Decimal("-108"))])
    return ledger


class ExportTests(unittest.TestCase):
    def setUp(self):
        if export_csv is None:
            self.fail("ledger.export is missing")

    def test_header_constant(self):
        self.assertEqual(CSV_HEADER, ["transaction_id", "date", "memo", "account", "amount", "currency"])

    def test_exact_output(self):
        self.assertEqual(export_csv(sample()), (
            "transaction_id,date,memo,account,amount,currency\n"
            '2,2024-01-05,"Paper, ""premium"" grade",4000,45.50,USD\n'
            '2,2024-01-05,"Paper, ""premium"" grade",1000,-45.50,USD\n'
            "1,2024-01-20,Client payment,1000,2000.00,USD\n"
            "1,2024-01-20,Client payment,4000,-2000.00,USD\n"
            "3,2024-01-25,EUR sale,1000,100.00,EUR\n"
            "3,2024-01-25,EUR sale,4000,-108.00,USD\n"
        ))

    def test_newline_in_memo_is_quoted(self):
        ledger = Ledger()
        ledger.open_account("1000", "Cash", "asset")
        ledger.open_account("4000", "Sales", "income")
        ledger.post(date(2024, 1, 1), "line one\nline two", [Posting("1000", Decimal("1")), Posting("4000", Decimal("-1"))])
        self.assertEqual(
            export_csv(ledger),
            "transaction_id,date,memo,account,amount,currency\n"
            '1,2024-01-01,"line one\nline two",1000,1.00,USD\n'
            '1,2024-01-01,"line one\nline two",4000,-1.00,USD\n',
        )

    def test_period_filter(self):
        text = export_csv(sample(), start=date(2024, 1, 6), end=date(2024, 1, 20))
        self.assertEqual(text.count("\n"), 3)
        self.assertIn("1,2024-01-20,Client payment,1000,2000.00,USD\n", text)
        self.assertNotIn("EUR sale", text)

    def test_empty_ledger(self):
        self.assertEqual(export_csv(Ledger()), "transaction_id,date,memo,account,amount,currency\n")

    def test_write_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "out.csv"
            write_csv(sample(), path, start=date(2024, 1, 25))
            content = path.read_bytes()
        self.assertEqual(content, b"transaction_id,date,memo,account,amount,currency\n3,2024-01-25,EUR sale,1000,100.00,EUR\n3,2024-01-25,EUR sale,4000,-108.00,USD\n")


if __name__ == "__main__":
    unittest.main()
