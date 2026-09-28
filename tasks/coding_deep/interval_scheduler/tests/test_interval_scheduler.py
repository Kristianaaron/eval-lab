import random
import time
import unittest

from solution import free_slots, max_concurrent, merge_intervals, schedule


class TestValidation(unittest.TestCase):
    BAD_INTERVALS = [
        (1,), (1, 2, 3), (3, 3), (5, 2), ("1", 2), (1, "2"), (None, 1), (True, 2),
        (1, False), "ab", 5, (1.0, 1.0),
    ]

    def test_bad_intervals_rejected_everywhere(self):
        for bad in self.BAD_INTERVALS:
            with self.assertRaises(ValueError):
                merge_intervals([(0, 1), bad])
            with self.assertRaises(ValueError):
                max_concurrent([bad])
            with self.assertRaises(ValueError):
                free_slots([bad], (0, 10))
            with self.assertRaises(ValueError):
                free_slots([(1, 2)], bad)
            with self.assertRaises(ValueError):
                schedule([(0, 1), bad])

    def test_non_sequence_input_rejected(self):
        with self.assertRaises(ValueError):
            merge_intervals(5)
        with self.assertRaises(ValueError):
            schedule(None)

    def test_inputs_not_mutated(self):
        data = [[5, 9], [1, 3], [2, 4]]
        snapshot = [list(x) for x in data]
        merge_intervals(data)
        max_concurrent(data)
        free_slots(data, [0, 10])
        schedule(data)
        self.assertEqual(data, snapshot)


class TestMerge(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(merge_intervals([]), [])

    def test_basic_merge_and_sort(self):
        self.assertEqual(
            merge_intervals([(8, 10), (1, 3), (2, 6), (15, 18)]), [(1, 6), (8, 10), (15, 18)]
        )

    def test_touching_intervals_merge(self):
        self.assertEqual(merge_intervals([(1, 3), (3, 5)]), [(1, 5)])
        self.assertEqual(merge_intervals([(3, 5), (1, 3), (5, 6)]), [(1, 6)])

    def test_contained_and_duplicate_intervals(self):
        self.assertEqual(merge_intervals([(1, 10), (2, 3), (4, 5), (1, 10)]), [(1, 10)])
        self.assertEqual(merge_intervals([(2, 3), (1, 10)]), [(1, 10)])

    def test_returns_tuples_and_keeps_number_types(self):
        out = merge_intervals([[1, 2.5], [2.5, 4]])
        self.assertEqual(out, [(1, 4)])
        self.assertIsInstance(out[0], tuple)
        self.assertIsInstance(out[0][0], int)
        self.assertIsInstance(out[0][1], int)
        out = merge_intervals([(0.5, 1.5), (3, 4)])
        self.assertEqual(out, [(0.5, 1.5), (3, 4)])

    def test_negative_and_float_bounds(self):
        self.assertEqual(
            merge_intervals([(-5, -1), (-1.5, 0.5), (10, 11)]), [(-5, 0.5), (10, 11)]
        )


class TestMaxConcurrent(unittest.TestCase):
    def test_empty_and_single(self):
        self.assertEqual(max_concurrent([]), 0)
        self.assertEqual(max_concurrent([(0, 1)]), 1)

    def test_half_open_touching_does_not_overlap(self):
        self.assertEqual(max_concurrent([(1, 3), (3, 5)]), 1)
        self.assertEqual(max_concurrent([(1, 3), (2, 5), (3, 4)]), 2)

    def test_peak_in_the_middle(self):
        self.assertEqual(max_concurrent([(0, 10), (2, 4), (3, 5), (4, 6), (9, 12)]), 3)

    def test_identical_intervals_stack(self):
        self.assertEqual(max_concurrent([(1, 2)] * 7), 7)

    def test_float_boundaries(self):
        self.assertEqual(max_concurrent([(0.0, 0.5), (0.25, 0.75), (0.5, 1.0)]), 2)


class TestFreeSlots(unittest.TestCase):
    def test_no_busy_returns_window(self):
        self.assertEqual(free_slots([], (9, 17)), [(9, 17)])
        out = free_slots([], [9, 17])
        self.assertEqual(out, [(9, 17)])
        self.assertIsInstance(out[0], tuple)

    def test_gaps_inside_window(self):
        self.assertEqual(
            free_slots([(10, 11), (13, 14)], (9, 17)), [(9, 10), (11, 13), (14, 17)]
        )

    def test_busy_outside_and_overlapping_window_edges(self):
        self.assertEqual(free_slots([(0, 9), (17, 20)], (9, 17)), [(9, 17)])
        self.assertEqual(free_slots([(5, 10), (16, 20)], (9, 17)), [(10, 16)])
        self.assertEqual(free_slots([(0, 100)], (9, 17)), [])
        self.assertEqual(free_slots([(9, 17)], (9, 17)), [])

    def test_unsorted_overlapping_busy(self):
        self.assertEqual(
            free_slots([(14, 15), (10, 12), (11, 13), (12, 12.5)], (10, 16)),
            [(13, 14), (15, 16)],
        )

    def test_touching_busy_leaves_no_zero_length_gap(self):
        self.assertEqual(free_slots([(9, 12), (12, 15)], (9, 17)), [(15, 17)])


class TestSchedule(unittest.TestCase):
    def assert_valid(self, meetings, rooms):
        self.assertEqual(len(rooms), len(meetings))
        self.assertTrue(all(isinstance(r, int) for r in rooms))
        self.assertEqual(sorted(set(rooms)), list(range(max(rooms) + 1)) if rooms else [])
        by_room = {}
        for (s, e), r in zip(meetings, rooms):
            by_room.setdefault(r, []).append((s, e))
        for ivs in by_room.values():
            ivs.sort()
            for (s1, e1), (s2, e2) in zip(ivs, ivs[1:]):
                self.assertLessEqual(e1, s2)
        self.assertEqual(max(rooms) + 1 if rooms else 0, max_concurrent(meetings))

    def test_empty(self):
        self.assertEqual(schedule([]), [])

    def test_deterministic_assignment(self):
        meetings = [(0, 30), (5, 10), (15, 20)]
        self.assertEqual(schedule(meetings), [0, 1, 1])
        meetings = [(7, 10), (2, 4)]
        self.assertEqual(schedule(meetings), [0, 0])

    def test_lowest_free_room_is_reused(self):
        # Room 0: [0,5); room 1: [1,3); room 2: [2,4). At t=5, rooms 1 and 2 are
        # free (1 freed at 3, 2 at 4) and room 0 frees at 5, so [5,6) -> room 0.
        meetings = [(0, 5), (1, 3), (2, 4), (4, 6), (5, 6)]
        self.assertEqual(schedule(meetings), [0, 1, 2, 1, 0])

    def test_ties_broken_by_end_then_index(self):
        meetings = [(0, 10), (0, 5), (0, 5)]
        self.assertEqual(schedule(meetings), [2, 0, 1])

    def test_random_assignments_are_valid_and_minimal(self):
        rng = random.Random(7)
        for _ in range(30):
            n = rng.randint(1, 40)
            meetings = []
            for _ in range(n):
                s = rng.randint(0, 50)
                meetings.append((s, s + rng.randint(1, 10)))
            self.assert_valid(meetings, schedule(meetings))


class TestPerformance(unittest.TestCase):
    def test_large_inputs_are_fast(self):
        rng = random.Random(123)
        n = 50000
        data = []
        for _ in range(n):
            s = rng.uniform(0, 100000)
            data.append((s, s + rng.uniform(0.1, 50)))
        start = time.perf_counter()
        merged = merge_intervals(data)
        peak = max_concurrent(data)
        slots = free_slots(data, (0, 100000))
        rooms = schedule(data)
        elapsed = time.perf_counter() - start
        self.assertLess(elapsed, 3.0)
        self.assertGreater(len(merged), 0)
        self.assertEqual(max(rooms) + 1, peak)
        self.assertEqual(len(rooms), n)
        self.assertTrue(all(s < e for s, e in slots))


if __name__ == "__main__":
    unittest.main()
