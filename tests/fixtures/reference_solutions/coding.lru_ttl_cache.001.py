import heapq
import time
from collections import OrderedDict


class LRUTTLCache:
    """LRU cache with per-key TTL, injectable clock and O(1) core operations."""

    def __init__(self, capacity, clock=time.monotonic):
        if isinstance(capacity, bool) or not isinstance(capacity, int) or capacity < 1:
            raise ValueError("capacity must be a positive int")
        self._capacity = capacity
        self._clock = clock
        self._data = OrderedDict()  # key -> [value, expires_at | None, version]
        self._heap = []  # (expires_at, seq, key, version) for entries with a TTL
        self._seq = 0
        self._hits = 0
        self._misses = 0
        self._evictions = 0
        self._expirations = 0

    @property
    def capacity(self):
        return self._capacity

    @staticmethod
    def _expired(expires_at, now):
        return expires_at is not None and now >= expires_at

    def _purge(self):
        now = self._clock()
        removed = 0
        heap = self._heap
        while heap and heap[0][0] <= now:
            _, _, key, version = heapq.heappop(heap)
            entry = self._data.get(key)
            if entry is not None and entry[2] == version:
                del self._data[key]
                removed += 1
        self._expirations += removed
        return removed

    def put(self, key, value, ttl=None):
        if ttl is not None:
            if isinstance(ttl, bool) or not isinstance(ttl, (int, float)) or ttl <= 0:
                raise ValueError("ttl must be a positive number or None")
        now = self._clock()
        expires_at = None if ttl is None else now + ttl
        self._seq += 1
        version = self._seq
        if key in self._data:
            self._data[key] = [value, expires_at, version]
            self._data.move_to_end(key)
        else:
            if len(self._data) >= self._capacity:
                self._purge()
                if len(self._data) >= self._capacity:
                    self._data.popitem(last=False)
                    self._evictions += 1
            self._data[key] = [value, expires_at, version]
        if expires_at is not None:
            heapq.heappush(self._heap, (expires_at, version, key, version))

    def get(self, key, default=None):
        entry = self._data.get(key)
        if entry is None:
            self._misses += 1
            return default
        if self._expired(entry[1], self._clock()):
            del self._data[key]
            self._expirations += 1
            self._misses += 1
            return default
        self._hits += 1
        self._data.move_to_end(key)
        return entry[0]

    def delete(self, key):
        if key in self._data:
            del self._data[key]
            return True
        return False

    def expire_stale(self):
        return self._purge()

    def keys(self):
        self._purge()
        return list(self._data.keys())

    def clear(self):
        self._data.clear()
        self._heap.clear()

    def stats(self):
        return {
            "hits": self._hits,
            "misses": self._misses,
            "evictions": self._evictions,
            "expirations": self._expirations,
        }

    def __len__(self):
        self._purge()
        return len(self._data)

    def __contains__(self, key):
        entry = self._data.get(key)
        if entry is None:
            return False
        return not self._expired(entry[1], self._clock())
