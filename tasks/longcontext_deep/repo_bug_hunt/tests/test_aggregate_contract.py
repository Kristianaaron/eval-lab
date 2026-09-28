"""Hidden tests for the flowkit statistics contract (README.md)."""

from __future__ import annotations

import math
import unittest

from flowkit.aggregate import Stats, group_by, percentile, summarize, summarize_field, summarize_groups
from flowkit.records import Record


class PercentileContract(unittest.TestCase):
    def test_p95_of_twenty_is_nineteenth(self) -> None:
        self.assertEqual(percentile(range(1, 21), 0.95), 19)

    def test_p95_of_thirty_is_twenty_ninth(self) -> None:
        self.assertEqual(percentile(range(1, 31), 0.95), 29)

    def test_p95_of_forty_is_thirty_eighth(self) -> None:
        self.assertEqual(percentile(range(1, 41), 0.95), 38)

    def test_p95_of_seventy_is_sixty_seventh(self) -> None:
        self.assertEqual(percentile(range(1, 71), 0.95), 67)

    def test_p50_of_twenty_is_tenth(self) -> None:
        self.assertEqual(percentile(range(1, 21), 0.5), 10)

    def test_p91_of_twenty_is_nineteenth(self) -> None:
        self.assertEqual(percentile(range(1, 21), 0.91), 19)

    def test_p100_is_maximum(self) -> None:
        self.assertEqual(percentile([5, 1, 9, 3], 1.0), 9)

    def test_small_p_is_minimum(self) -> None:
        self.assertEqual(percentile([5, 1, 9, 3], 0.01), 1)

    def test_unsorted_input(self) -> None:
        self.assertEqual(percentile([30, 10, 20, 40, 50], 0.6), 30)

    def test_invalid_p_raises(self) -> None:
        with self.assertRaises(ValueError):
            percentile([1, 2], 0.0)
        with self.assertRaises(ValueError):
            percentile([1, 2], 1.5)
        with self.assertRaises(ValueError):
            percentile([1, 2], -0.1)

    def test_empty_raises(self) -> None:
        with self.assertRaises(ValueError):
            percentile([], 0.5)


class SummarizeContract(unittest.TestCase):
    def test_median_even_count_is_mean_of_middle(self) -> None:
        self.assertEqual(summarize(range(1, 21)).median, 10.5)

    def test_median_odd_count_is_middle(self) -> None:
        self.assertEqual(summarize([7, 1, 3]).median, 3)

    def test_median_two_values(self) -> None:
        self.assertEqual(summarize([4, 10]).median, 7)

    def test_p95_matches_percentile(self) -> None:
        values = [float(v) for v in range(100, 130)]
        self.assertEqual(summarize(values).p95, percentile(values, 0.95))
        self.assertEqual(summarize(values).p95, 128.0)

    def test_basic_fields(self) -> None:
        s = summarize([2, 4, 4, 4, 5, 5, 7, 9])
        self.assertIsInstance(s, Stats)
        self.assertEqual((s.count, s.total, s.minimum, s.maximum), (8, 40.0, 2.0, 9.0))
        self.assertEqual(s.mean, 5.0)
        self.assertEqual(s.median, 4.5)

    def test_mean_rounded_six_places(self) -> None:
        s = summarize([1, 2, 2])
        self.assertEqual(s.mean, round(5 / 3, 6))

    def test_accepts_strings_and_ints(self) -> None:
        s = summarize(["1", 2, 3.0])
        self.assertEqual(s.total, 6.0)

    def test_empty_raises(self) -> None:
        with self.assertRaises(ValueError):
            summarize([])

    def test_single_value(self) -> None:
        s = summarize([42])
        self.assertEqual((s.median, s.p95, s.minimum, s.maximum), (42.0, 42.0, 42.0, 42.0))

    def test_large_sample_p95(self) -> None:
        values = list(range(1, 1001))
        self.assertEqual(summarize(values).p95, 950.0)
        self.assertTrue(math.isclose(summarize(values).median, 500.5))


class GroupingContract(unittest.TestCase):
    def _records(self) -> list[Record]:
        rows = [("a", 10), ("b", 1), ("a", 30), ("b", 3), ("a", 20), ("c", 5)]
        return [Record({"svc": s, "lat": v}) for s, v in rows]

    def test_group_by_preserves_order(self) -> None:
        groups = group_by(self._records(), lambda r: r["svc"])
        self.assertEqual(list(groups), ["a", "b", "c"])
        self.assertEqual([r["lat"] for r in groups["a"]], [10, 30, 20])

    def test_summarize_field_skips_missing(self) -> None:
        recs = self._records() + [Record({"svc": "a"})]
        self.assertEqual(summarize_field(recs, "lat").count, 6)

    def test_summarize_groups_sorted_keys_and_stats(self) -> None:
        out = summarize_groups(self._records(), lambda r: r["svc"], "lat")
        self.assertEqual(list(out), ["a", "b", "c"])
        self.assertEqual(out["a"].median, 20.0)
        self.assertEqual(out["b"].median, 2.0)
        self.assertEqual(out["a"].p95, 30.0)


if __name__ == "__main__":
    unittest.main()
