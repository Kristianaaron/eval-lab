import time
import unittest

from solution import LRUTTLCache


class FakeClock:
    def __init__(self, now=0.0):
        self.now = now

    def __call__(self):
        return self.now

    def advance(self, dt):
        self.now += dt


def make(capacity=3, now=0.0):
    clock = FakeClock(now)
    return LRUTTLCache(capacity, clock=clock), clock


class TestConstruction(unittest.TestCase):
    def test_capacity_attribute(self):
        cache, _ = make(5)
        self.assertEqual(cache.capacity, 5)

    def test_invalid_capacity_raises(self):
        for bad in (0, -1, 2.5, "3", None, True):
            with self.assertRaises(ValueError):
                LRUTTLCache(bad)

    def test_default_clock_works(self):
        cache = LRUTTLCache(2)
        cache.put("a", 1, ttl=1000)
        self.assertEqual(cache.get("a"), 1)
        self.assertIn("a", cache)

    def test_initial_stats(self):
        cache, _ = make()
        self.assertEqual(
            cache.stats(), {"hits": 0, "misses": 0, "evictions": 0, "expirations": 0}
        )
        self.assertEqual(len(cache), 0)


class TestBasicOps(unittest.TestCase):
    def test_put_get_roundtrip_and_none_value(self):
        cache, _ = make()
        cache.put("a", 1)
        cache.put("b", None)
        self.assertEqual(cache.get("a"), 1)
        self.assertIsNone(cache.get("b", "fallback"))
        self.assertIn("b", cache)
        self.assertEqual(cache.get("zzz", "fallback"), "fallback")
        self.assertEqual(cache.stats()["hits"], 2)
        self.assertEqual(cache.stats()["misses"], 1)

    def test_delete_semantics(self):
        cache, _ = make()
        cache.put("a", 1)
        self.assertTrue(cache.delete("a"))
        self.assertFalse(cache.delete("a"))
        self.assertNotIn("a", cache)
        self.assertEqual(cache.stats(), {"hits": 0, "misses": 0, "evictions": 0, "expirations": 0})

    def test_overwrite_updates_value_and_recency(self):
        cache, _ = make(2)
        cache.put("a", 1)
        cache.put("b", 2)
        cache.put("a", 10)
        self.assertEqual(cache.keys(), ["b", "a"])
        cache.put("c", 3)  # evicts b, the LRU
        self.assertEqual(cache.keys(), ["a", "c"])
        self.assertEqual(cache.get("a"), 10)
        self.assertEqual(cache.stats()["evictions"], 1)

    def test_clear_keeps_counters(self):
        cache, _ = make()
        cache.put("a", 1)
        cache.get("a")
        cache.get("b")
        cache.clear()
        self.assertEqual(len(cache), 0)
        self.assertEqual(cache.keys(), [])
        self.assertEqual(cache.stats()["hits"], 1)
        self.assertEqual(cache.stats()["misses"], 1)

    def test_stats_returns_fresh_dict(self):
        cache, _ = make()
        s = cache.stats()
        s["hits"] = 99
        self.assertEqual(cache.stats()["hits"], 0)

    def test_hashable_keys_of_mixed_types(self):
        cache, _ = make(4)
        cache.put(1, "int")
        cache.put((1, 2), "tuple")
        cache.put(None, "none")
        cache.put(frozenset({3}), "fs")
        self.assertEqual(cache.get((1, 2)), "tuple")
        self.assertEqual(cache.get(None), "none")
        self.assertEqual(cache.get(frozenset({3})), "fs")
        self.assertEqual(cache.get(1), "int")
        self.assertEqual(len(cache), 4)


class TestLRUOrder(unittest.TestCase):
    def test_eviction_is_least_recently_used(self):
        cache, _ = make(3)
        cache.put("a", 1)
        cache.put("b", 2)
        cache.put("c", 3)
        cache.get("a")  # a becomes MRU; b is LRU
        cache.put("d", 4)
        self.assertEqual(cache.keys(), ["c", "a", "d"])
        self.assertNotIn("b", cache)
        self.assertEqual(cache.stats()["evictions"], 1)

    def test_contains_and_keys_do_not_touch_recency_or_stats(self):
        cache, _ = make(2)
        cache.put("a", 1)
        cache.put("b", 2)
        self.assertIn("a", cache)
        self.assertNotIn("nope", cache)
        cache.keys()
        cache.put("c", 3)  # a still LRU
        self.assertEqual(cache.keys(), ["b", "c"])
        self.assertEqual(cache.stats()["hits"], 0)
        self.assertEqual(cache.stats()["misses"], 0)

    def test_miss_does_not_change_order(self):
        cache, _ = make(2)
        cache.put("a", 1)
        cache.put("b", 2)
        cache.get("missing")
        cache.put("c", 3)
        self.assertEqual(cache.keys(), ["b", "c"])

    def test_capacity_one(self):
        cache, _ = make(1)
        cache.put("a", 1)
        cache.put("b", 2)
        self.assertEqual(cache.keys(), ["b"])
        self.assertEqual(cache.get("a"), None)
        self.assertEqual(cache.stats()["evictions"], 1)
        self.assertEqual(cache.stats()["misses"], 1)


class TestTTL(unittest.TestCase):
    def test_invalid_ttl_rejected_without_side_effects(self):
        cache, _ = make()
        cache.put("a", 1)
        for bad in (0, -1, "5", True, [1]):
            with self.assertRaises(ValueError):
                cache.put("a", 2, ttl=bad)
            with self.assertRaises(ValueError):
                cache.put("new", 2, ttl=bad)
        self.assertEqual(cache.get("a"), 1)
        self.assertEqual(len(cache), 1)

    def test_expiry_boundary_is_exclusive(self):
        cache, clock = make()
        cache.put("a", 1, ttl=10)
        clock.advance(9.999)
        self.assertEqual(cache.get("a"), 1)
        clock.advance(0.001)
        self.assertEqual(cache.get("a", "gone"), "gone")
        s = cache.stats()
        self.assertEqual((s["hits"], s["misses"], s["expirations"]), (1, 1, 1))

    def test_expired_entry_removed_by_get(self):
        cache, clock = make()
        cache.put("a", 1, ttl=1)
        clock.advance(5)
        self.assertIsNone(cache.get("a"))
        self.assertFalse(cache.delete("a"))
        self.assertEqual(cache.stats()["expirations"], 1)

    def test_contains_respects_expiry_without_counting(self):
        cache, clock = make()
        cache.put("a", 1, ttl=2)
        self.assertIn("a", cache)
        clock.advance(2)
        self.assertNotIn("a", cache)
        self.assertEqual(cache.stats()["misses"], 0)

    def test_len_and_keys_exclude_expired(self):
        cache, clock = make(5)
        cache.put("a", 1, ttl=1)
        cache.put("b", 2, ttl=5)
        cache.put("c", 3)
        clock.advance(1)
        self.assertEqual(len(cache), 2)
        self.assertEqual(cache.keys(), ["b", "c"])
        clock.advance(4)
        self.assertEqual(cache.keys(), ["c"])
        self.assertEqual(len(cache), 1)

    def test_overwrite_resets_ttl(self):
        cache, clock = make()
        cache.put("a", 1, ttl=5)
        clock.advance(4)
        cache.put("a", 2, ttl=5)
        clock.advance(4)
        self.assertEqual(cache.get("a"), 2)
        cache.put("a", 3)  # now permanent
        clock.advance(1000)
        self.assertEqual(cache.get("a"), 3)

    def test_expire_stale_counts_and_returns(self):
        cache, clock = make(10)
        for i in range(5):
            cache.put(i, i, ttl=i + 1)
        cache.put("perm", 0)
        clock.advance(3)
        self.assertEqual(cache.expire_stale(), 3)
        self.assertEqual(cache.expire_stale(), 0)
        self.assertEqual(cache.keys(), [3, 4, "perm"])
        self.assertEqual(cache.stats()["expirations"], 3)

    def test_full_cache_prefers_purging_expired_over_evicting(self):
        cache, clock = make(3)
        cache.put("a", 1, ttl=1)
        cache.put("b", 2)
        cache.put("c", 3)
        clock.advance(1)
        cache.put("d", 4)
        s = cache.stats()
        self.assertEqual(s["evictions"], 0)
        self.assertEqual(s["expirations"], 1)
        self.assertEqual(cache.keys(), ["b", "c", "d"])
        cache.put("e", 5)  # nothing expired: evict LRU (b)
        self.assertEqual(cache.keys(), ["c", "d", "e"])
        self.assertEqual(cache.stats()["evictions"], 1)

    def test_int_clock_and_float_ttl(self):
        clock = FakeClock(100)
        cache = LRUTTLCache(2, clock=clock)
        cache.put("a", 1, ttl=0.5)
        clock.now = 100.25
        self.assertIn("a", cache)
        clock.now = 100.5
        self.assertNotIn("a", cache)


class TestPerformance(unittest.TestCase):
    def test_many_operations_are_fast(self):
        clock = FakeClock(0.0)
        cache = LRUTTLCache(1000, clock=clock)
        start = time.perf_counter()
        for i in range(20000):
            cache.put(i, i, ttl=None if i % 3 else 5000)
            cache.get(i // 2)
            if i % 7 == 0:
                clock.advance(0.5)
        elapsed = time.perf_counter() - start
        self.assertLess(elapsed, 2.0)
        self.assertEqual(len(cache), 1000)
        s = cache.stats()
        self.assertEqual(s["hits"] + s["misses"], 20000)
        self.assertGreaterEqual(s["evictions"], 19000)


if __name__ == "__main__":
    unittest.main()
