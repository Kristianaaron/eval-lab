import unittest
from decimal import Decimal

from ledger.errors import LedgerError

try:  # both are part of the feature under test: a missing module is a failure, not a skip
    from ledger.currency import RateTable
    from ledger.errors import CurrencyError
except ImportError:  # pragma: no cover
    RateTable = CurrencyError = None


class RateTableTests(unittest.TestCase):
    def setUp(self):
        if RateTable is None or CurrencyError is None:
            self.fail("ledger.currency.RateTable / ledger.errors.CurrencyError are missing")

    def test_base_is_normalised(self):
        table = RateTable("eur")
        self.assertEqual(table.base, "EUR")
        self.assertEqual(RateTable().base, "USD")
        self.assertEqual(table.rate("Eur"), Decimal(1))

    def test_set_and_get_rate(self):
        table = RateTable()
        table.set_rate("eur", "1.08")
        table.set_rate("GBP", Decimal("1.25"))
        table.set_rate("jpy", 1)
        self.assertEqual(table.rate("EUR"), Decimal("1.08"))
        self.assertEqual(table.rate("gbp"), Decimal("1.25"))
        self.assertEqual(table.rates(), {"EUR": Decimal("1.08"), "GBP": Decimal("1.25"), "JPY": Decimal("1")})
        self.assertEqual(table.currencies(), ["EUR", "GBP", "JPY", "USD"])
        table.set_rate("EUR", "1.10")
        self.assertEqual(table.rate("EUR"), Decimal("1.10"))

    def test_errors(self):
        table = RateTable()
        self.assertTrue(issubclass(CurrencyError, LedgerError))
        with self.assertRaises(CurrencyError) as ctx:
            table.rate("CHF")
        self.assertEqual(str(ctx.exception), "unknown currency: CHF")
        with self.assertRaises(CurrencyError) as ctx:
            table.set_rate("USD", "1")
        self.assertEqual(str(ctx.exception), "cannot set a rate for the base currency")
        with self.assertRaises(CurrencyError) as ctx:
            table.set_rate("EUR", "0")
        self.assertEqual(str(ctx.exception), "rate must be positive")
        with self.assertRaises(CurrencyError):
            table.set_rate("EUR", "-2")
        with self.assertRaises(CurrencyError) as ctx:
            table.set_rate("euro", "1")
        self.assertEqual(str(ctx.exception), "invalid currency code: 'euro'")
        with self.assertRaises(CurrencyError):
            table.rate("E1R")
        with self.assertRaises(CurrencyError):
            RateTable("us")

    def test_convert(self):
        table = RateTable()
        table.set_rate("EUR", "1.08")
        table.set_rate("GBP", "1.25")
        self.assertEqual(table.convert(Decimal("100"), "EUR", "USD"), Decimal("108.00"))
        self.assertEqual(table.convert(Decimal("100"), "USD", "EUR"), Decimal("92.59"))
        self.assertEqual(table.convert(Decimal("100"), "EUR", "GBP"), Decimal("86.40"))
        self.assertEqual(table.convert(Decimal("-45.50"), "usd", "eur"), Decimal("-42.13"))
        self.assertEqual(table.convert(Decimal("0.005"), "EUR", "USD"), Decimal("0.01"))

    def test_same_currency_is_identity(self):
        table = RateTable()
        amount = Decimal("12.345")
        self.assertEqual(table.convert(amount, "chf", "CHF"), amount)  # no rate needed, no rounding
        self.assertEqual(table.convert(Decimal("7"), "USD", "usd"), Decimal("7"))
        with self.assertRaises(CurrencyError):
            table.convert(Decimal("1"), "CHF", "USD")


if __name__ == "__main__":
    unittest.main()
