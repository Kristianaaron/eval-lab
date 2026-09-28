Implement a bounded, least-recently-used (LRU) cache in which every entry may carry its own time-to-live (TTL). Use only the Python standard library.

## Required API

```
class LRUTTLCache:
    def __init__(self, capacity, clock=time.monotonic): ...
    def put(self, key, value, ttl=None) -> None: ...
    def get(self, key, default=None): ...
    def delete(self, key) -> bool: ...
    def expire_stale(self) -> int: ...
    def keys(self) -> list: ...
    def clear(self) -> None: ...
    def stats(self) -> dict: ...
    def __len__(self) -> int: ...
    def __contains__(self, key) -> bool: ...
    capacity  # read-only attribute (the value passed to the constructor)
```

## Semantics

- `capacity` must be an `int` (a `bool` is **not** accepted) and `>= 1`; otherwise raise `ValueError`.
- `clock` is a zero-argument callable returning the current time in seconds as an `int` or `float`. All time arithmetic uses this clock; never call `time.time`/`time.monotonic` directly when a clock is injected.
- `put(key, value, ttl=None)`:
  - `ttl=None` means the entry never expires. Otherwise `ttl` must be an `int` or `float` (not `bool`) and `> 0`; otherwise raise `ValueError` and leave the cache unchanged.
  - The entry is live while `clock() < insert_time + ttl` (at exactly `insert_time + ttl` it is expired).
  - Putting a key that already exists (live or expired) replaces its value and its TTL (the expiry is recomputed from the current time), and makes it the most recently used. No eviction happens in that case.
  - Inserting a **new** key when the cache already holds `capacity` entries: first remove all expired entries (each counted as an *expiration*); if the cache is still full, evict the least recently used entry (counted as an *eviction*). Exactly one eviction happens at most per `put`.
- `get(key, default=None)`: if `key` is present and live, count a *hit*, mark the entry most recently used and return its value. If the key is absent, count a *miss* and return `default`. If the key is present but expired, remove it, count an *expiration* **and** a *miss*, and return `default`.
- `delete(key)`: remove the key if stored (live or expired) and return `True`; return `False` if absent. Does not affect hit/miss/eviction/expiration counters.
- `expire_stale()`: remove every expired entry, count each as an expiration, and return the number removed.
- `keys()`: the live keys ordered from least recently used to most recently used. Must not change recency or counters. May purge expired entries (counted as expirations).
- `len(cache)`: the number of live entries. May purge expired entries (counted as expirations).
- `key in cache`: `True` only if the key is present and live. Must not change recency. Must not count as a hit or a miss.
- `clear()`: remove all entries. Counters are **not** reset.
- `stats()`: a new `dict` with exactly the keys `"hits"`, `"misses"`, `"evictions"`, `"expirations"` (all `int`, starting at 0).
- Recency is changed only by `put` and by a successful `get` (a hit).
- Keys may be any hashable object; values may be anything, including `None`.
- All operations except `expire_stale`, `keys`, `len` and the expiry purge must run in O(1) average time. A workload of 20,000 mixed `put`/`get` calls against a cache of capacity 1,000 must finish well within one second.

Reply with exactly one fenced ```python block containing a complete module that defines these names. Do not include tests or example usage outside the block.
