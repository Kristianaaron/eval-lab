import time
import unittest

from solution import ExpressionError, evaluate


class TestLiterals(unittest.TestCase):
    def test_integer_literal_is_int(self):
        v = evaluate("42")
        self.assertEqual(v, 42)
        self.assertIsInstance(v, int)

    def test_float_literals(self):
        self.assertEqual(evaluate("3.14"), 3.14)
        self.assertEqual(evaluate(".5"), 0.5)
        self.assertEqual(evaluate("2."), 2.0)
        self.assertIsInstance(evaluate("2."), float)
        self.assertEqual(evaluate("1e3"), 1000.0)
        self.assertIsInstance(evaluate("1e3"), float)
        self.assertEqual(evaluate("2.5E-2"), 0.025)

    def test_whitespace_is_ignored(self):
        self.assertEqual(evaluate("  1 +\t2\n* 3 "), 7)


class TestPrecedence(unittest.TestCase):
    def test_basic_precedence(self):
        self.assertEqual(evaluate("1 + 2 * 3"), 7)
        self.assertEqual(evaluate("(1 + 2) * 3"), 9)
        self.assertEqual(evaluate("2 * 3 ** 2"), 18)
        self.assertEqual(evaluate("10 - 4 - 3"), 3)
        self.assertEqual(evaluate("100 / 10 / 2"), 5.0)
        self.assertEqual(evaluate("7 % 4 * 2"), 6)

    def test_power_is_right_associative(self):
        self.assertEqual(evaluate("2 ** 3 ** 2"), 512)
        self.assertEqual(evaluate("(2 ** 3) ** 2"), 64)

    def test_unary_minus_and_power(self):
        self.assertEqual(evaluate("-2 ** 2"), -4)
        self.assertEqual(evaluate("(-2) ** 2"), 4)
        self.assertEqual(evaluate("2 ** -1"), 0.5)
        self.assertEqual(evaluate("2 ** -2 ** 2"), 0.0625)
        self.assertEqual(evaluate("--3"), 3)
        self.assertEqual(evaluate("-+-3"), 3)
        self.assertEqual(evaluate("3 - -2"), 5)
        self.assertEqual(evaluate("-x", {"x": 5}), -5)

    def test_python_division_semantics(self):
        self.assertEqual(evaluate("7 / 2"), 3.5)
        v = evaluate("6 / 3")
        self.assertEqual(v, 2.0)
        self.assertIsInstance(v, float)
        self.assertEqual(evaluate("7 // 2"), 3)
        self.assertEqual(evaluate("-7 // 2"), -4)
        self.assertEqual(evaluate("-7 % 3"), 2)
        self.assertEqual(evaluate("7.5 // 2"), 3.0)
        self.assertEqual(evaluate("5.5 % 2"), 1.5)

    def test_power_types(self):
        v = evaluate("2 ** 10")
        self.assertEqual(v, 1024)
        self.assertIsInstance(v, int)
        self.assertEqual(evaluate("4 ** 0.5"), 2.0)
        self.assertEqual(evaluate("2 ** 100"), 2 ** 100)

    def test_nested_parentheses(self):
        self.assertEqual(evaluate("((((1 + 2)) * (3 + (4))))"), 21)
        self.assertEqual(evaluate("(1)"), 1)


class TestFunctionsAndVariables(unittest.TestCase):
    def test_min_max_variadic(self):
        self.assertEqual(evaluate("min(3, 1, 2)"), 1)
        self.assertEqual(evaluate("max(3, 1, 2)"), 3)
        self.assertEqual(evaluate("min(5)"), 5)
        self.assertEqual(evaluate("max(1, 2.5, -3)"), 2.5)
        self.assertEqual(evaluate("min(1 + 1, 2 * 3, 10 - 9)"), 1)

    def test_abs_and_round(self):
        self.assertEqual(evaluate("abs(-3)"), 3)
        self.assertEqual(evaluate("abs(-2.5)"), 2.5)
        self.assertEqual(evaluate("round(2.5)"), 2)
        self.assertEqual(evaluate("round(3.5)"), 4)
        self.assertEqual(evaluate("round(3.14159, 2)"), 3.14)
        self.assertEqual(evaluate("round(1234, -2)"), 1200)
        self.assertIsInstance(evaluate("round(2.7)"), int)

    def test_nested_calls_and_expressions_in_args(self):
        self.assertEqual(evaluate("max(min(1, 2), abs(-3) - 1, 0) ** 2"), 4)
        self.assertEqual(evaluate("round(max(1.26, 1.24) * 2, 1)"), 2.5)

    def test_variables(self):
        env = {"x": 3, "y_2": 4.0, "_z": -1}
        self.assertEqual(evaluate("x * y_2 + _z", env), 11.0)
        self.assertEqual(evaluate("x ** 2 + 2 * x + 1", {"x": 5}), 36)
        self.assertEqual(env, {"x": 3, "y_2": 4.0, "_z": -1})

    def test_variables_default_none_and_empty(self):
        self.assertEqual(evaluate("1 + 1", None), 2)
        self.assertEqual(evaluate("1 + 1", {}), 2)


class TestErrors(unittest.TestCase):
    def assert_error(self, expr, variables=None):
        with self.assertRaises(ExpressionError):
            evaluate(expr, variables)

    def test_error_is_a_value_error(self):
        self.assertTrue(issubclass(ExpressionError, ValueError))

    def test_syntax_errors(self):
        for expr in [
            "", "   ", "(", ")", "(1", "1)", "2 +", "* 3", "2 3", "2 & 3", "$",
            "1 + 2 )", "()", "1 +* 2", "2 ** ", "1..2", "1 2 3", "min(1,)",
            "max(,1)", "abs 1", "1 +", "+", "-", "3 //", "1 /// 2", "(1 + 2",
        ]:
            self.assert_error(expr)

    def test_unknown_names(self):
        self.assert_error("x")
        self.assert_error("x + 1", {"y": 1})
        self.assert_error("foo(1)")
        self.assert_error("sqrt(4)")
        self.assert_error("MIN(1, 2)")

    def test_arity_errors(self):
        for expr in ["min()", "max()", "abs()", "abs(1, 2)", "round()", "round(1, 2, 3)"]:
            self.assert_error(expr)

    def test_function_and_variable_misuse(self):
        self.assert_error("min + 1")
        self.assert_error("abs")
        self.assert_error("x(1)", {"x": 2})

    def test_division_by_zero(self):
        for expr in ["1 / 0", "1 // 0", "1 % 0", "0 ** -1", "1 / (2 - 2)", "1.5 % 0.0"]:
            self.assert_error(expr)

    def test_bad_variable_values(self):
        self.assert_error("x", {"x": "1"})
        self.assert_error("x", {"x": True})
        self.assert_error("x + 1", {"x": None})
        self.assert_error("x", {"x": [1]})

    def test_complex_and_overflow(self):
        self.assert_error("(-8) ** 0.5")
        self.assert_error("10.0 ** 400")

    def test_no_python_eval_backdoor(self):
        for expr in ["__import__('os')", "1 if 1 else 2", "[1]", "1 and 2", "x.y", "'a'"]:
            self.assert_error(expr, {"x": 1})


class TestPerformance(unittest.TestCase):
    def test_long_left_associative_chain(self):
        expr = "+".join(["1"] * 3000)
        self.assertEqual(evaluate(expr), 3000)
        expr = "-".join(["1"] * 3000)
        self.assertEqual(evaluate(expr), 1 - 2999)

    def test_many_evaluations_are_fast(self):
        expr = "max(a * 2 + b, abs(c - 10) // 3, round(d / 7, 2)) - (a + b) % 5 ** 2"
        env = {"a": 3, "b": 4, "c": 5, "d": 6}
        expected = evaluate(expr, env)
        start = time.perf_counter()
        for i in range(2000):
            env["a"] = i % 10
            evaluate(expr, env)
        elapsed = time.perf_counter() - start
        env["a"] = 3
        self.assertEqual(evaluate(expr, env), expected)
        self.assertLess(elapsed, 2.0)


if __name__ == "__main__":
    unittest.main()
