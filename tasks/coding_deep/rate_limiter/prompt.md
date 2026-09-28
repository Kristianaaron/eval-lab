Implement two per-key rate limiters with an injectable clock. Only the standard library may be used.

## Required API

```
class SlidingWindowLimiter:
    def __init__(self, limit, window, clock=time.monotonic): ...
    def allow(self, key) -> bool: ...
    def remaining(self, key) -> int: ...
    def retry_after(self, key) -> float: ...
    def reset(self, key=None) -> None: ...

class TokenBucketLimiter:
    def __init__(self, capacity, refill_rate, clock=time.monotonic): ...
    def allow(self, key, tokens=1) -> bool: ...
    def remaining(self, key) -> float: ...
    def retry_after(self, key, tokens=1) -> float: ...
    def reset(self, key=None) -> None: ...
```

`clock` is a zero-argument callable returning the current time in seconds (`int` or `float`); every time computation must go through it. Keys are arbitrary hashable objects and are completely independent of each other. `reset(key)` forgets the state of one key; `reset()` with no argument forgets every key. A key that has never been seen (or has been reset) is in its initial state.

## SlidingWindowLimiter (sliding log)

- `limit` must be an `int` (not `bool`) `>= 1`; `window` must be an `int` or `float` (not `bool`) `> 0`. Otherwise raise `ValueError`.
- An *active* event is an allowed request whose timestamp `t` satisfies `now < t + window` (an event recorded at `t` stops counting at exactly `t + window`).
- `allow(key)`: if the key currently has fewer than `limit` active events, record an event at `now` and return `True`; otherwise return `False` and record nothing. Denied requests never count.
- `remaining(key)`: `limit` minus the number of active events (never negative). Does not record anything.
- `retry_after(key)`: `0.0` if `allow(key)` would succeed right now; otherwise the number of seconds until the oldest active event stops counting (`oldest_t + window - now`). Always a `float`. Does not record anything.
- Memory for a key must not grow beyond `limit` events.

## TokenBucketLimiter

- `capacity` and `refill_rate` must be `int` or `float` (not `bool`) and `> 0`; otherwise raise `ValueError`.
- Each key has a bucket that starts **full** (`capacity` tokens) the first time it is seen. Tokens refill continuously at `refill_rate` tokens per second, never exceeding `capacity`: at any moment `tokens = min(capacity, tokens_at_last_update + (now - last_update) * refill_rate)`.
- `allow(key, tokens=1)`: `tokens` (the cost) must be an `int` or `float` (not `bool`) with `0 < tokens <= capacity`, else raise `ValueError` (without touching state). If the bucket currently holds at least `tokens`, subtract them and return `True`; otherwise return `False` and leave the bucket unchanged (refill still applies).
- `remaining(key)`: the current number of tokens as a `float` after applying refill; for an unseen key this is `float(capacity)`.
- `retry_after(key, tokens=1)`: `0.0` if a request of that cost would be allowed right now; otherwise `(tokens - current_tokens) / refill_rate`. Same validation of `tokens` as `allow`.
- Both `allow` and `remaining` must never report more than `capacity` tokens and must never report negative tokens.

## Precision

Do your arithmetic so that results are exact for inputs representable as `float` (tests compare with a tolerance of `1e-9`). Comparisons such as "has at least `tokens`" are plain `>=` on floats; no epsilon fudging.

## Performance

20,000 `allow` calls spread over 100 keys against either limiter must complete well under one second; the sliding window must not scan more than the expired prefix of a key's log per call.

Reply with exactly one fenced ```python block containing a complete module that defines these names. Do not include tests or example usage outside the block.
