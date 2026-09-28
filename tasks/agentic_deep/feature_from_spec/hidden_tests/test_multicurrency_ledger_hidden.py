import json
import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

from ledger import store
from ledger.book import Ledger
from ledger.errors import UnbalancedTransactionError
from ledger.models import Posting

try:
    from ledger.currency import RateTable
    from ledger.errors import CurrencyError
except ImportError:  # pragma: no cover
    RateTable = CurrencyError = None


class _FeatureCase(unittest.TestCase):
    def setUp(self):
        if RateTable is None or CurrencyError is None:
            self.fail("ledger.currency.RateTable / ledger.errors.CurrencyError are missing")


def ledger_with_rates():
    ledger = Ledger("USD")
    ledger.rates.set_rate("EUR", "1.08")
    ledger.rates.set_rate("GBP", "1.25")
    ledger.open_account("1000", "Cash", "asset")
    ledger.open_account("1100", "Euro account", "asset")
    ledger.open_account("4000", "Sales", "income")
    return ledger


class PostingTests(_FeatureCase):
    def test_positional_currency_and_normalisation(self):
        leg = Posting("1000", Decimal("5"), "eur")
        self.assertEqual(leg.currency, "EUR")
        self.assertIsNone(Posting("1000", Decimal("5")).currency)
        self.assertEqual(Posting(account="1000", amount=Decimal("5"), currency="GBP").currency, "GBP")

    def test_invalid_currency(self):
        with self.assertRaises(CurrencyError):
            Posting("1000", Decimal("5"), "EURO")


class LedgerCurrencyTests(_FeatureCase):
    def test_base_currency_and_rate_table(self):
        ledger = Ledger("eur")
        self.assertEqual(ledger.base_currency, "EUR")
        self.assertIsInstance(ledger.rates, RateTable)
        self.assertEqual(ledger.rates.base, "EUR")
        self.assertEqual(Ledger().base_currency, "USD")

    def test_base_currency_is_filled_in(self):
        ledger = ledger_with_rates()
        txn = ledger.post(date(2024, 1, 1), "x", [Posting("1000", Decimal("5")), Posting("4000", Decimal("-5"))])
        self.assertEqual([p.currency for p in txn.postings], ["USD", "USD"])
        self.assertEqual([p.currency for p in ledger.transactions()[0].postings], ["USD", "USD"])

    def test_balances_in_base_after_conversion(self):
        ledger = ledger_with_rates()
        txn = ledger.post(
            date(2024, 1, 1), "EUR sale", [Posting("1100", Decimal("100"), "EUR"), Posting("4000", Decimal("-108"))]
        )
        self.assertEqual(txn.postings[0].currency, "EUR")
        self.assertEqual(ledger.balance("1100"), Decimal("108.00"))
        self.assertEqual(ledger.balance("1100", currency="EUR"), Decimal("100.00"))
        self.assertEqual(ledger.balance("1100", currency="gbp"), Decimal("86.40"))

    def test_unbalanced_in_base(self):
        ledger = ledger_with_rates()
        with self.assertRaises(UnbalancedTransactionError) as ctx:
            ledger.post(date(2024, 1, 1), "x", [Posting("1100", Decimal("100"), "EUR"), Posting("4000", Decimal("-100"))])
        self.assertEqual(ctx.exception.difference, Decimal("8.00"))
        self.assertEqual(ledger.transactions(), [])

    def test_unknown_currency_rejected_before_storing(self):
        ledger = ledger_with_rates()
        with self.assertRaises(CurrencyError):
            ledger.post(date(2024, 1, 1), "x", [Posting("1100", Decimal("1"), "CHF"), Posting("4000", Decimal("-1"), "CHF")])
        self.assertEqual(ledger.transactions(), [])
        with self.assertRaises(CurrencyError):
            ledger.balance("1000", currency="CHF")

    def test_balance_rounds_per_posting(self):
        ledger = ledger_with_rates()
        # 3 x 0.01 USD -> each converts to 0.01 EUR (0.00926 -> 0.01), summed 0.03, not 0.03/1.08 -> 0.03 vs 0.02
        for _ in range(3):
            ledger.post(date(2024, 1, 1), "cent", [Posting("1000", Decimal("0.01")), Posting("4000", Decimal("-0.01"))])
        self.assertEqual(ledger.balance("1000", currency="EUR"), Decimal("0.03"))
        # 3 x 0.01 EUR -> each 0.01 USD (0.0108 -> 0.01): 0.03 not 0.0324 -> 0.03; and 3 x 0.05 EUR -> 0.05 USD each (0.054) 0.15 not 0.16
        for _ in range(3):
            ledger.post(date(2024, 1, 2), "five", [Posting("1100", Decimal("0.05"), "EUR"), Posting("4000", Decimal("-0.05"), "EUR")])
        self.assertEqual(ledger.balance("1100"), Decimal("0.15"))
        self.assertEqual(ledger.balance("1100", currency="EUR"), Decimal("0.15"))

    def test_amount_for(self):
        ledger = ledger_with_rates()
        txn = ledger.post(
            date(2024, 1, 1), "split",
            [Posting("1000", Decimal("10")), Posting("1000", Decimal("10"), "EUR"), Posting("4000", Decimal("-20.80"))],
        )
        self.assertEqual(txn.amount_for("1000", ledger.rates, "USD"), Decimal("20.80"))
        self.assertEqual(txn.amount_for("1000", ledger.rates, "EUR"), Decimal("19.26"))
        self.assertEqual(txn.amount_for("4000", ledger.rates, "GBP"), Decimal("-16.64"))
        self.assertEqual(txn.amount_for("9999", ledger.rates, "USD"), Decimal("0"))

    def test_rates_are_not_versioned(self):
        ledger = ledger_with_rates()
        ledger.post(date(2024, 1, 1), "x", [Posting("1100", Decimal("100"), "EUR"), Posting("4000", Decimal("-108"))])
        ledger.rates.set_rate("EUR", "1.10")
        self.assertEqual(ledger.balance("1100"), Decimal("110.00"))


class StoreTests(_FeatureCase):
    def test_document_format(self):
        ledger = ledger_with_rates()
        ledger.post(date(2024, 1, 1), "x", [Posting("1100", Decimal("100"), "EUR"), Posting("4000", Decimal("-108"))])
        doc = store.to_document(ledger)
        self.assertEqual(doc["base_currency"], "USD")
        self.assertEqual(doc["rates"], {"EUR": "1.08", "GBP": "1.25"})
        self.assertEqual(list(doc["rates"]), ["EUR", "GBP"])
        self.assertEqual(
            doc["transactions"][0]["postings"],
            [{"account": "1100", "amount": "100.00", "currency": "EUR"},
             {"account": "4000", "amount": "-108.00", "currency": "USD"}],
        )

    def test_round_trip_through_file(self):
        ledger = ledger_with_rates()
        ledger.post(date(2024, 1, 1), "x", [Posting("1100", Decimal("100"), "EUR"), Posting("4000", Decimal("-108"))])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "books.json"
            store.save(ledger, path)
            reloaded = store.load(path)
        self.assertEqual(reloaded.base_currency, "USD")
        self.assertEqual(reloaded.rates.rates(), {"EUR": Decimal("1.08"), "GBP": Decimal("1.25")})
        self.assertEqual(reloaded.transactions()[0].postings[0].currency, "EUR")
        self.assertEqual(reloaded.balance("1100", currency="EUR"), Decimal("100.00"))

    def test_legacy_document_loads(self):
        raw = {
            "version": 1,
            "accounts": [{"code": "1000", "name": "Cash", "kind": "asset"}, {"code": "4000", "name": "Sales", "kind": "income"}],
            "transactions": [{"id": 7, "date": "2024-02-01", "memo": "old", "postings": [
                {"account": "1000", "amount": "3.00"}, {"account": "4000", "amount": "-3.00"}]}],
        }
        ledger = store.from_document(raw)
        self.assertEqual(ledger.base_currency, "USD")
        self.assertEqual(ledger.rates.rates(), {})
        self.assertEqual([p.currency for p in ledger.transactions()[0].postings], ["USD", "USD"])
        self.assertEqual(ledger.balance("1000"), Decimal("3.00"))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "old.json"
            path.write_text(json.dumps(raw))
            self.assertEqual(store.load(path).balance("4000"), Decimal("-3.00"))

    def test_non_usd_base_round_trip(self):
        ledger = Ledger("EUR")
        ledger.rates.set_rate("USD", "0.92")
        ledger.open_account("1000", "Cash", "asset")
        ledger.open_account("4000", "Sales", "income")
        ledger.post(date(2024, 1, 1), "x", [Posting("1000", Decimal("100"), "USD"), Posting("4000", Decimal("-92"))])
        reloaded = store.from_document(json.loads(json.dumps(store.to_document(ledger))))
        self.assertEqual(reloaded.base_currency, "EUR")
        self.assertEqual(reloaded.balance("1000"), Decimal("92.00"))
        self.assertEqual(reloaded.balance("1000", currency="USD"), Decimal("100.00"))


if __name__ == "__main__":
    unittest.main()
