import unittest
from decimal import Decimal

from inventory.errors import ValidationError
from inventory.models import Product
from inventory.pricing import DiscountRule, best_rule, discounted_unit_price, quote


def product(price, category="general"):
    return Product(sku="X", name="X", unit_price=Decimal(price), category=category)


class RoundingHiddenTests(unittest.TestCase):
    def test_half_up_cases(self):
        cases = [
            ("10.70", "75", "2.68"),   # 2.675
            ("4.02", "75", "1.01"),    # 1.005
            ("0.50", "75", "0.13"),    # 0.125
            ("13.34", "75", "3.34"),   # 3.335
            ("19.995", "0", "20.00"),
        ]
        for price, pct, expected in cases:
            rule = DiscountRule("r", "percent", Decimal(pct))
            self.assertEqual(discounted_unit_price(Decimal(price), rule), Decimal(expected), price)

    def test_result_has_two_places(self):
        rule = DiscountRule("r", "percent", Decimal("10"))
        result = discounted_unit_price(Decimal("5"), rule)
        self.assertEqual(result, Decimal("4.50"))
        self.assertEqual(result.as_tuple().exponent, -2)
        self.assertIsInstance(result, Decimal)

    def test_fixed_rule_rounds_half_up(self):
        rule = DiscountRule("r", "fixed", Decimal("0.005"))
        self.assertEqual(discounted_unit_price(Decimal("2.68"), rule), Decimal("2.68"))
        rule = DiscountRule("r", "fixed", Decimal("0.004"))
        self.assertEqual(discounted_unit_price(Decimal("1.00"), rule), Decimal("1.00"))

    def test_fixed_rule_floors_at_zero(self):
        rule = DiscountRule("r", "fixed", Decimal("5"))
        self.assertEqual(discounted_unit_price(Decimal("3"), rule), Decimal("0.00"))

    def test_quote_with_rounding_sensitive_values(self):
        q = quote(product("10.70"), 4, rules=[DiscountRule("c", "percent", Decimal("75"))],
                  tax_rate=Decimal("7.5"))
        self.assertEqual(q.unit_price, Decimal("2.68"))
        self.assertEqual(q.subtotal, Decimal("10.72"))
        self.assertEqual(q.tax, Decimal("0.80"))
        self.assertEqual(q.total, Decimal("11.52"))
        self.assertEqual(q.rule_name, "c")

    def test_best_rule_ties_go_to_first(self):
        rules = [DiscountRule("a", "percent", Decimal("50")), DiscountRule("b", "fixed", Decimal("5"))]
        self.assertEqual(best_rule(product("10"), 1, rules).name, "a")

    def test_no_applicable_rule(self):
        rules = [DiscountRule("bulk", "percent", Decimal("50"), min_quantity=100)]
        self.assertIsNone(best_rule(product("10"), 5, rules))
        q = quote(product("10.005"), 1, rules=rules)
        self.assertEqual(q.unit_price, Decimal("10.01"))
        self.assertIsNone(q.rule_name)

    def test_quote_validation(self):
        with self.assertRaises(ValidationError):
            quote(product("1"), 0)
        with self.assertRaises(ValidationError):
            DiscountRule("bad", "coupon", Decimal("1"))


if __name__ == "__main__":
    unittest.main()
