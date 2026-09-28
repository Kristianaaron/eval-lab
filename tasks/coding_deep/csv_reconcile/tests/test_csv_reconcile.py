import time
import unittest

from solution import ReconcileError, reconcile, values_equal


LEFT = [
    {"id": "41", "name": "old", "price": "1.0"},
    {"id": "42", "name": "widget", "price": "1.5", "qty": "3"},
    {"id": "43", "name": "gizmo", "price": "2", "qty": "1"},
    {"id": "45", "name": "same", "price": "9.99", "qty": "0"},
]
RIGHT = [
    {"id": "42", "name": "widget", "price": "2.0", "qty": "4"},
    {"id": "43", "name": "gizmo", "price": "2.00", "qty": "1"},
    {"id": "44", "name": "new", "price": "5"},
    {"id": "45", "name": "same", "price": "9.99", "qty": "0"},
]


class TestValuesEqual(unittest.TestCase):
    def test_numeric_coercion(self):
        self.assertTrue(values_equal("1.0", "1"))
        self.assertTrue(values_equal("1e3", "1000"))
        self.assertTrue(values_equal("+5", "5"))
        self.assertTrue(values_equal("007", "7"))
        self.assertTrue(values_equal(".5", "0.50"))
        self.assertTrue(values_equal("2.", "2"))
        self.assertTrue(values_equal("-0", "0"))
        self.assertTrue(values_equal("1.5E-1", "0.15"))
        self.assertTrue(values_equal(3, "3.0"))
        self.assertTrue(values_equal(2.5, "2.5"))

    def test_numeric_comparison_is_exact(self):
        self.assertFalse(values_equal("12345678901234567890", "12345678901234567891"))
        self.assertFalse(values_equal("0.1", "0.10000000000000001"))
        self.assertTrue(values_equal("0.1", "0.10000000000000000"))
        self.assertFalse(values_equal("1", "1.0000000000000000001"))

    def test_string_rules(self):
        self.assertTrue(values_equal("abc", "abc"))
        self.assertFalse(values_equal("abc", "ABC"))
        self.assertTrue(values_equal("abc", " abc "))
        self.assertTrue(values_equal("", ""))
        self.assertTrue(values_equal(None, ""))
        self.assertTrue(values_equal(None, "  "))
        self.assertFalse(values_equal("", "0"))
        self.assertFalse(values_equal(None, "0"))
        self.assertFalse(values_equal("1,000", "1000"))
        self.assertFalse(values_equal("0x10", "16"))
        self.assertFalse(values_equal("1_000", "1000"))
        self.assertFalse(values_equal("inf", "inf2"))
        self.assertFalse(values_equal("nan", "0"))
        self.assertFalse(values_equal("1.", "1.x"))
        self.assertFalse(values_equal("1 000", "1000"))


class TestReconcileBasics(unittest.TestCase):
    def setUp(self):
        self.res = reconcile(LEFT, RIGHT, "id")

    def test_partition(self):
        self.assertEqual(list(self.res.added), ["44"])
        self.assertEqual(list(self.res.removed), ["41"])
        self.assertEqual(list(self.res.changed), ["42"])
        self.assertEqual(self.res.unchanged, ["43", "45"])

    def test_rows_are_original_objects(self):
        self.assertIs(self.res.added["44"], RIGHT[2])
        self.assertIs(self.res.removed["41"], LEFT[0])

    def test_changed_details_sorted_fields(self):
        self.assertEqual(self.res.changed["42"], {"price": ("1.5", "2.0"), "qty": ("3", "4")})
        self.assertEqual(list(self.res.changed["42"]), ["price", "qty"])

    def test_summary_format(self):
        self.assertEqual(
            self.res.summary(),
            "added=1 removed=1 changed=1 unchanged=2\n"
            "- 41\n"
            "+ 44\n"
            "~ 42: price='1.5'->'2.0', qty='3'->'4'",
        )

    def test_inputs_not_mutated(self):
        left = [dict(r) for r in LEFT]
        right = [dict(r) for r in RIGHT]
        reconcile(left, right, "id")
        self.assertEqual(left, LEFT)
        self.assertEqual(right, RIGHT)


class TestReconcileRules(unittest.TestCase):
    def test_empty_inputs(self):
        res = reconcile([], [], "id")
        self.assertEqual((res.added, res.removed, res.changed, res.unchanged), ({}, {}, {}, []))
        self.assertEqual(res.summary(), "added=0 removed=0 changed=0 unchanged=0")
        res = reconcile([], [{"id": "1"}], "id")
        self.assertEqual(res.summary(), "added=1 removed=0 changed=0 unchanged=0\n+ 1")

    def test_sorted_key_order(self):
        left = [{"id": k} for k in ("b", "a", "10", "9")]
        right = [{"id": k} for k in ("z", "c", "b", "a", "10", "9")]
        res = reconcile(left, right, "id")
        self.assertEqual(list(res.added), ["c", "z"])
        self.assertEqual(res.unchanged, ["10", "9", "a", "b"])

    def test_missing_field_treated_as_empty(self):
        left = [{"id": "1", "note": ""}, {"id": "2"}]
        right = [{"id": "1"}, {"id": "2", "note": "x"}]
        res = reconcile(left, right, "id")
        self.assertEqual(res.unchanged, ["1"])
        self.assertEqual(res.changed, {"2": {"note": ("", "x")}})

    def test_changed_values_are_normalised_not_stripped(self):
        left = [{"id": "1", "v": " a "}, {"id": "2", "v": None}, {"id": "3", "v": 5}]
        right = [{"id": "1", "v": "b"}, {"id": "2", "v": "z"}, {"id": "3", "v": "6.0"}]
        res = reconcile(left, right, "id")
        self.assertEqual(res.changed["1"], {"v": (" a ", "b")})
        self.assertEqual(res.changed["2"], {"v": ("", "z")})
        self.assertEqual(res.changed["3"], {"v": ("5", "6.0")})

    def test_whitespace_and_numeric_equivalence_in_rows(self):
        left = [{"id": "1", "a": " x ", "b": "1.0", "c": "1e2"}]
        right = [{"id": "1", "a": "x", "b": "1", "c": "100.0"}]
        self.assertEqual(reconcile(left, right, "id").unchanged, ["1"])

    def test_ignore_fields(self):
        left = [{"id": "1", "updated": "mon", "v": "1"}]
        right = [{"id": "1", "updated": "tue", "v": "1"}]
        self.assertEqual(list(reconcile(left, right, "id").changed), ["1"])
        res = reconcile(left, right, "id", ignore_fields=["updated"])
        self.assertEqual(res.unchanged, ["1"])
        self.assertEqual(res.changed, {})

    def test_key_field_never_compared(self):
        left = [{"id": "1"}]
        right = [{"id": "1"}]
        res = reconcile(left, right, "id")
        self.assertEqual(res.unchanged, ["1"])

    def test_keys_compared_as_exact_strings(self):
        left = [{"id": "1"}, {"id": " 2"}]
        right = [{"id": "1.0"}, {"id": "2"}]
        res = reconcile(left, right, "id")
        self.assertEqual(list(res.removed), [" 2", "1"])
        self.assertEqual(list(res.added), ["1.0", "2"])

    def test_non_string_key_values_normalised(self):
        left = [{"id": 7, "v": "a"}, {"id": None, "v": "n"}]
        right = [{"id": "7", "v": "a"}, {"id": "", "v": "n"}]
        res = reconcile(left, right, "id")
        self.assertEqual(res.unchanged, ["", "7"])


class TestCompositeKey(unittest.TestCase):
    def test_composite_key_tuples_and_summary(self):
        left = [
            {"region": "eu", "sku": "a1", "qty": "1"},
            {"region": "us", "sku": "a1", "qty": "2"},
        ]
        right = [
            {"region": "eu", "sku": "a1", "qty": "1.0"},
            {"region": "us", "sku": "a1", "qty": "3"},
            {"region": "us", "sku": "b2", "qty": "0"},
        ]
        res = reconcile(left, right, ("region", "sku"))
        self.assertEqual(res.unchanged, [("eu", "a1")])
        self.assertEqual(list(res.added), [("us", "b2")])
        self.assertEqual(res.changed, {("us", "a1"): {"qty": ("2", "3")}})
        self.assertEqual(
            res.summary(),
            "added=1 removed=0 changed=1 unchanged=1\n+ us|b2\n~ us|a1: qty='2'->'3'",
        )

    def test_composite_key_as_list_of_one(self):
        res = reconcile([{"id": "1", "v": "a"}], [{"id": "1", "v": "b"}], ["id"])
        self.assertEqual(res.changed, {("1",): {"v": ("a", "b")}})
        self.assertEqual(res.summary(), "added=0 removed=0 changed=1 unchanged=0\n~ 1: v='a'->'b'")

    def test_composite_components_never_compared(self):
        left = [{"a": "1", "b": "2", "v": "x"}]
        right = [{"a": "1", "b": "2", "v": "x"}]
        self.assertEqual(reconcile(left, right, ["a", "b"]).unchanged, [("1", "2")])


class TestErrors(unittest.TestCase):
    def test_bad_key_argument(self):
        for bad in (None, 5, [], ["id", 3], {"id": 1}):
            with self.assertRaises(ValueError):
                reconcile([], [], bad)

    def test_duplicate_keys(self):
        with self.assertRaises(ReconcileError) as cm:
            reconcile([{"id": "7"}, {"id": "7"}], [], "id")
        self.assertIn("left", str(cm.exception))
        self.assertIn("7", str(cm.exception))
        with self.assertRaises(ReconcileError) as cm:
            reconcile([], [{"id": "x"}, {"id": "x"}], "id")
        self.assertIn("right", str(cm.exception))
        self.assertIn("x", str(cm.exception))

    def test_missing_key_field_and_bad_rows(self):
        with self.assertRaises(ReconcileError):
            reconcile([{"name": "a"}], [], "id")
        with self.assertRaises(ReconcileError):
            reconcile([], [{"id": "1", "sku": "a"}], ("id", "region"))
        with self.assertRaises(ReconcileError):
            reconcile([["id", "1"]], [], "id")
        with self.assertRaises(ReconcileError):
            reconcile([None], [], "id")

    def test_summary_repr_of_values_with_quotes(self):
        left = [{"id": "1", "v": "it's"}]
        right = [{"id": "1", "v": 'say "hi"'}]
        res = reconcile(left, right, "id")
        self.assertEqual(
            res.summary(),
            "added=0 removed=0 changed=1 unchanged=0\n~ 1: v=" + repr("it's") + "->" + repr('say "hi"'),
        )


class TestPerformance(unittest.TestCase):
    def test_large_inputs(self):
        n = 20000
        left = [{"id": str(i), "a": str(i), "b": f"{i}.0", "c": "x"} for i in range(n)]
        right = [{"id": str(i), "a": f"{i}.00", "b": str(i), "c": "x" if i % 2 else "y"}
                 for i in range(1, n + 1)]
        start = time.perf_counter()
        res = reconcile(left, right, "id")
        summary = res.summary()
        elapsed = time.perf_counter() - start
        self.assertLess(elapsed, 3.0)
        self.assertEqual(len(res.added), 1)
        self.assertEqual(len(res.removed), 1)
        self.assertEqual(len(res.changed) + len(res.unchanged), n - 1)
        self.assertEqual(len(res.changed), (n - 1) // 2)  # even ids differ in column c
        self.assertTrue(summary.startswith("added=1 removed=1 "))


if __name__ == "__main__":
    unittest.main()
