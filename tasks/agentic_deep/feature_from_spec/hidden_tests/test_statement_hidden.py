import unittest
from datetime import date
from decimal import Decimal

from ledger import reports
from ledger.book import Ledger
from ledger.errors import UnknownAccountError, ValidationError
from ledger.models import Posting


def sample():
    ledger = Ledger()
    ledger.rates.set_rate("EUR", "1.08")
    ledger.open_account("1000", "Cash", "asset")
    ledger.open_account("4000", "Sales", "income")
    ledger.open_account("6000", "Office", "expense")
    ledger.post(date(2024, 1, 2), "Opening float", [Posting("1000", Decimal("1000")), Posting("4000", Decimal("-1000"))])
    ledger.post(date(2024, 1, 5), "Office supplies", [Posting("6000", Decimal("45.50")), Posting("1000", Decimal("-45.50"))])
    ledger.post(date(2024, 1, 20), "Client payment", [Posting("1000", Decimal("2000")), Posting("4000", Decimal("-2000"))])
    ledger.post(date(2024, 1, 25), "EUR sale", [Posting("1000", Decimal("100"), "EUR"), Posting("4000", Decimal("-108"))])
    ledger.post(date(2024, 2, 3), "February rent payment for the office", [Posting("6000", Decimal("800")), Posting("1000", Decimal("-800"))])
    return ledger


class StatementTests(unittest.TestCase):
    def test_exact_layout(self):
        text = reports.statement(sample(), "1000", date(2024, 1, 3), date(2024, 1, 31))
        self.assertEqual(text, "\n".join([
            "Statement for 1000 Cash",
            "Period 2024-01-03 to 2024-01-31 (USD)",
            "Opening balance                                       1,000.00",
            "2024-01-05  Office supplies                 -45.50      954.50",
            "2024-01-20  Client payment                2,000.00    2,954.50",
            "2024-01-25  EUR sale                        108.00    3,062.50",
            "Closing balance                                       3,062.50",
        ]))
        self.assertFalse(text.endswith("\n"))
        for line in text.splitlines()[2:]:
            self.assertEqual(len(line), 62, line)

    def test_currency_conversion_and_memo_truncation(self):
        text = reports.statement(sample(), "1000", date(2024, 1, 25), date(2024, 2, 28), currency="eur")
        self.assertEqual(text.splitlines(), [
            "Statement for 1000 Cash",
            "Period 2024-01-25 to 2024-02-28 (EUR)",
            "Opening balance                                       2,735.65",
            "2024-01-25  EUR sale                        100.00    2,835.65",
            "2024-02-03  February rent payment for      -740.74    2,094.91",
            "Closing balance                                       2,094.91",
        ])

    def test_empty_period(self):
        text = reports.statement(sample(), "6000", date(2024, 3, 1), date(2024, 3, 31))
        self.assertEqual(text.splitlines(), [
            "Statement for 6000 Office",
            "Period 2024-03-01 to 2024-03-31 (USD)",
            "Opening balance                                         845.50",
            "Closing balance                                         845.50",
        ])

    def test_opening_excludes_start_day_transactions(self):
        text = reports.statement(sample(), "1000", date(2024, 1, 2), date(2024, 1, 2))
        self.assertEqual(text.splitlines()[2], "Opening balance                                           0.00")
        self.assertEqual(text.splitlines()[3], "2024-01-02  Opening float                 1,000.00    1,000.00")
        self.assertEqual(text.splitlines()[-1], "Closing balance                                       1,000.00")

    def test_same_account_twice_in_one_transaction_is_one_line(self):
        ledger = Ledger()
        ledger.open_account("1000", "Cash", "asset")
        ledger.open_account("4000", "Sales", "income")
        ledger.post(date(2024, 1, 1), "split", [Posting("1000", Decimal("3")), Posting("1000", Decimal("4")), Posting("4000", Decimal("-7"))])
        lines = reports.statement(ledger, "1000", date(2024, 1, 1), date(2024, 1, 1)).splitlines()
        self.assertEqual(len(lines), 5)
        self.assertEqual(lines[3], "2024-01-01  split                             7.00        7.00")

    def test_errors(self):
        with self.assertRaises(UnknownAccountError):
            reports.statement(sample(), "9999", date(2024, 1, 1), date(2024, 1, 31))
        with self.assertRaises(ValidationError):
            reports.statement(sample(), "1000", date(2024, 1, 31), date(2024, 1, 1))


if __name__ == "__main__":
    unittest.main()
