import time
import unittest

from solution import SlidingWindowLimiter, TokenBucketLimiter


class FakeClock:
    def __init__(self, now=0.0):
        self.now = now

    def __call__(self):
        return self.now


class TestSlidingWindowValidation(unittest.TestCase):
    def test_bad_limit(self):
        for bad in (0, -1, 1.5, "1", True, None):
            with self.assertRaises(ValueError):
                SlidingWindowLimiter(bad, 10)

    def test_bad_window(self):
        for bad in (0, -1, "10", True, None):
            with self.assertRaises(ValueError):
                SlidingWindowLimiter(3, bad)

    def test_default_clock(self):
        lim = SlidingWindowLimiter(2, 60)
        self.assertTrue(lim.allow("k"))
        self.assertTrue(lim.allow("k"))
        self.assertFalse(lim.allow("k"))
        self.assertGreater(lim.retry_after("k"), 0.0)


class TestSlidingWindow(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock(0.0)
        self.lim = SlidingWindowLimiter(3, 10, clock=self.clock)

    def test_basic_allow_and_deny(self):
        for t in (0, 1, 2):
            self.clock.now = t
            self.assertTrue(self.lim.allow("a"))
        self.clock.now = 3
        self.assertFalse(self.lim.allow("a"))
        self.assertEqual(self.lim.remaining("a"), 0)

    def test_retry_after_matches_oldest_event(self):
        for t in (0, 1, 2):
            self.clock.now = t
            self.lim.allow("a")
        self.clock.now = 3
        self.assertAlmostEqual(self.lim.retry_after("a"), 7.0, places=9)
        self.clock.now = 9.5
        self.assertAlmostEqual(self.lim.retry_after("a"), 0.5, places=9)
        self.assertIsInstance(self.lim.retry_after("a"), float)

    def test_events_expire_at_exact_boundary(self):
        for t in (0, 1, 2):
            self.clock.now = t
            self.lim.allow("a")
        self.clock.now = 9.999999
        self.assertFalse(self.lim.allow("a"))
        self.clock.now = 10
        self.assertEqual(self.lim.remaining("a"), 1)
        self.assertEqual(self.lim.retry_after("a"), 0.0)
        self.assertTrue(self.lim.allow("a"))
        self.assertFalse(self.lim.allow("a"))
        self.clock.now = 11
        self.assertTrue(self.lim.allow("a"))  # event at t=1 expired

    def test_denied_requests_are_not_recorded(self):
        for _ in range(3):
            self.lim.allow("a")
        for _ in range(50):
            self.assertFalse(self.lim.allow("a"))
        self.clock.now = 10
        self.assertEqual(self.lim.remaining("a"), 3)
        self.assertTrue(self.lim.allow("a"))

    def test_remaining_and_retry_after_do_not_record(self):
        self.assertEqual(self.lim.remaining("a"), 3)
        self.assertEqual(self.lim.retry_after("a"), 0.0)
        for _ in range(10):
            self.lim.remaining("a")
            self.lim.retry_after("a")
        self.assertEqual(self.lim.remaining("a"), 3)
        self.assertTrue(self.lim.allow("a"))
        self.assertEqual(self.lim.remaining("a"), 2)

    def test_keys_are_independent(self):
        for _ in range(3):
            self.assertTrue(self.lim.allow("a"))
        self.assertFalse(self.lim.allow("a"))
        self.assertTrue(self.lim.allow("b"))
        self.assertTrue(self.lim.allow(("tuple", 1)))
        self.assertEqual(self.lim.remaining("b"), 2)
        self.assertEqual(self.lim.remaining("a"), 0)

    def test_reset_single_and_all(self):
        for k in ("a", "b"):
            for _ in range(3):
                self.lim.allow(k)
        self.lim.reset("a")
        self.assertEqual(self.lim.remaining("a"), 3)
        self.assertEqual(self.lim.remaining("b"), 0)
        self.lim.reset()
        self.assertEqual(self.lim.remaining("b"), 3)
        self.lim.reset("never-seen")  # must not raise

    def test_float_window_precision(self):
        clock = FakeClock(0.0)
        lim = SlidingWindowLimiter(1, 0.3, clock=clock)
        clock.now = 0.1
        self.assertTrue(lim.allow("k"))
        clock.now = 0.2
        self.assertAlmostEqual(lim.retry_after("k"), 0.2, places=9)
        clock.now = 0.1 + 0.3
        self.assertTrue(lim.allow("k"))

    def test_sliding_not_fixed_window(self):
        lim = SlidingWindowLimiter(2, 10, clock=self.clock)
        self.clock.now = 8
        lim.allow("a")
        self.clock.now = 9
        lim.allow("a")
        self.clock.now = 10  # a fixed window [0, 10) would reset here
        self.assertFalse(lim.allow("a"))
        self.assertAlmostEqual(lim.retry_after("a"), 8.0, places=9)
        self.clock.now = 18
        self.assertTrue(lim.allow("a"))


class TestTokenBucketValidation(unittest.TestCase):
    def test_bad_capacity_and_rate(self):
        for bad in (0, -1, "5", True, None):
            with self.assertRaises(ValueError):
                TokenBucketLimiter(bad, 1)
            with self.assertRaises(ValueError):
                TokenBucketLimiter(5, bad)

    def test_bad_cost_does_not_change_state(self):
        clock = FakeClock(0.0)
        lim = TokenBucketLimiter(5, 1, clock=clock)
        for bad in (0, -1, 6, "1", True, None):
            with self.assertRaises(ValueError):
                lim.allow("k", bad)
            with self.assertRaises(ValueError):
                lim.retry_after("k", bad)
        self.assertAlmostEqual(lim.remaining("k"), 5.0, places=9)
        self.assertTrue(lim.allow("k", 5))

    def test_default_clock(self):
        lim = TokenBucketLimiter(2, 1000)
        self.assertTrue(lim.allow("k"))
        self.assertTrue(lim.allow("k"))
        self.assertLessEqual(lim.remaining("k"), 2.0)


class TestTokenBucket(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock(0.0)
        self.lim = TokenBucketLimiter(5, 2, clock=self.clock)  # 5 tokens, 2/s

    def test_starts_full_and_drains(self):
        self.assertAlmostEqual(self.lim.remaining("a"), 5.0, places=9)
        self.assertIsInstance(self.lim.remaining("a"), float)
        for _ in range(5):
            self.assertTrue(self.lim.allow("a"))
        self.assertFalse(self.lim.allow("a"))
        self.assertAlmostEqual(self.lim.remaining("a"), 0.0, places=9)

    def test_refill_and_cap(self):
        for _ in range(5):
            self.lim.allow("a")
        self.clock.now = 1.0
        self.assertAlmostEqual(self.lim.remaining("a"), 2.0, places=9)
        self.clock.now = 100.0
        self.assertAlmostEqual(self.lim.remaining("a"), 5.0, places=9)
        self.assertTrue(self.lim.allow("a", 5))
        self.assertFalse(self.lim.allow("a"))

    def test_cost_and_retry_after(self):
        self.assertTrue(self.lim.allow("a", 4))
        self.assertAlmostEqual(self.lim.remaining("a"), 1.0, places=9)
        self.assertEqual(self.lim.retry_after("a", 1), 0.0)
        self.assertAlmostEqual(self.lim.retry_after("a", 3), 1.0, places=9)
        self.assertAlmostEqual(self.lim.retry_after("a", 5), 2.0, places=9)
        self.assertFalse(self.lim.allow("a", 3))
        self.clock.now = 0.5
        self.assertAlmostEqual(self.lim.retry_after("a", 3), 0.5, places=9)
        self.clock.now = 1.0
        self.assertEqual(self.lim.retry_after("a", 3), 0.0)
        self.assertTrue(self.lim.allow("a", 3))
        self.assertAlmostEqual(self.lim.remaining("a"), 0.0, places=9)

    def test_fractional_costs_and_refill(self):
        lim = TokenBucketLimiter(1.0, 0.5, clock=self.clock)
        self.assertTrue(lim.allow("k", 0.75))
        self.assertAlmostEqual(lim.remaining("k"), 0.25, places=9)
        self.assertFalse(lim.allow("k", 0.5))
        self.assertAlmostEqual(lim.retry_after("k", 0.5), 0.5, places=9)
        self.clock.now = 0.5
        self.assertTrue(lim.allow("k", 0.5))
        self.assertAlmostEqual(lim.remaining("k"), 0.0, places=9)
        self.clock.now = 10.5
        self.assertAlmostEqual(lim.remaining("k"), 1.0, places=9)

    def test_denied_does_not_consume(self):
        self.lim.allow("a", 5)
        self.clock.now = 0.25  # 0.5 tokens
        self.assertFalse(self.lim.allow("a", 1))
        self.assertAlmostEqual(self.lim.remaining("a"), 0.5, places=9)
        self.clock.now = 0.5
        self.assertTrue(self.lim.allow("a", 1))

    def test_keys_independent_and_reset(self):
        self.lim.allow("a", 5)
        self.assertTrue(self.lim.allow("b", 5))
        self.assertFalse(self.lim.allow("a"))
        self.lim.reset("a")
        self.assertAlmostEqual(self.lim.remaining("a"), 5.0, places=9)
        self.assertAlmostEqual(self.lim.remaining("b"), 0.0, places=9)
        self.lim.reset()
        self.assertAlmostEqual(self.lim.remaining("b"), 5.0, places=9)

    def test_integer_clock(self):
        clock = FakeClock(100)
        lim = TokenBucketLimiter(3, 1, clock=clock)
        lim.allow("k", 3)
        clock.now = 102
        self.assertAlmostEqual(lim.remaining("k"), 2.0, places=9)
        self.assertAlmostEqual(lim.retry_after("k", 3), 1.0, places=9)

    def test_steady_state_throughput(self):
        lim = TokenBucketLimiter(10, 4, clock=self.clock)
        allowed = 0
        for i in range(1, 401):
            self.clock.now = i * 0.05  # 20 requests per second over 20 seconds
            if lim.allow("k"):
                allowed += 1
        # Burst of 10 plus 4/s * 20s = 90 (boundary rounding may add one).
        self.assertGreaterEqual(allowed, 89)
        self.assertLessEqual(allowed, 91)


class TestPerformance(unittest.TestCase):
    def test_many_calls_are_fast(self):
        clock = FakeClock(0.0)
        sw = SlidingWindowLimiter(50, 1.0, clock=clock)
        tb = TokenBucketLimiter(50, 100.0, clock=clock)
        start = time.perf_counter()
        for i in range(20000):
            clock.now = i * 0.0001
            key = i % 100
            sw.allow(key)
            tb.allow(key)
            if i % 1000 == 0:
                sw.retry_after(key)
                tb.retry_after(key)
        elapsed = time.perf_counter() - start
        self.assertLess(elapsed, 2.0)


if __name__ == "__main__":
    unittest.main()
