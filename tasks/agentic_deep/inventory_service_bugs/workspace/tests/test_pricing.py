import unittest
from decimal import Decimal

from inventory.models import Product
from inventory.pricing import DiscountRule, best_rule, discounted_unit_price, money, quote


def product(price="10.70", category="stationery"):
    return Product(sku="PEN-01", name="Gel pen", unit_price=Decimal(price), category=category)


class MoneyTests(unittest.TestCase):
    def test_money_rounds_half_up(self):
        self.assertEqual(money(Decimal("2.675")), Decimal("2.68"))
        self.assertEqual(money(Decimal("2.674")), Decimal("2.67"))


class DiscountTests(unittest.TestCase):
    def test_percent_discount(self):
        rule = DiscountRule("quarter", "percent", Decimal("25"))
        self.assertEqual(discounted_unit_price(Decimal("10.70"), rule), Decimal("8.03"))

    def test_percent_discount_rounds_half_up(self):
        rule = DiscountRule("clearance", "percent", Decimal("75"))
        # 10.70 * 0.25 = 2.675 -> 2.68 under our half-up convention
        self.assertEqual(discounted_unit_price(Decimal("10.70"), rule), Decimal("2.68"))

    def test_fixed_discount_never_goes_negative(self):
        rule = DiscountRule("voucher", "fixed", Decimal("20"))
        self.assertEqual(discounted_unit_price(Decimal("10.70"), rule), Decimal("0.00"))

    def test_best_rule_prefers_lowest_price(self):
        rules = [
            DiscountRule("small", "percent", Decimal("10")),
            DiscountRule("bulk", "percent", Decimal("30"), min_quantity=10),
            DiscountRule("other-category", "percent", Decimal("90"), category="toys"),
        ]
        self.assertEqual(best_rule(product(), 5, rules).name, "small")
        self.assertEqual(best_rule(product(), 10, rules).name, "bulk")

    def test_quote_totals(self):
        q = quote(product(), 3, rules=[DiscountRule("small", "percent", Decimal("10"))],
                  tax_rate=Decimal("8"))
        self.assertEqual(q.unit_price, Decimal("9.63"))
        self.assertEqual(q.subtotal, Decimal("28.89"))
        self.assertEqual(q.tax, Decimal("2.31"))
        self.assertEqual(q.total, Decimal("31.20"))
        self.assertEqual(q.rule_name, "small")


if __name__ == "__main__":
    unittest.main()
