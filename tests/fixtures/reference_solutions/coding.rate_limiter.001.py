import time
from collections import deque


def _is_num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


class SlidingWindowLimiter:
    def __init__(self, limit, window, clock=time.monotonic):
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ValueError("limit must be an int >= 1")
        if not _is_num(window) or window <= 0:
            raise ValueError("window must be a positive number")
        self.limit = limit
        self.window = window
        self._clock = clock
        self._logs = {}

    def _log(self, key):
        log = self._logs.get(key)
        if log is None:
            log = deque()
            self._logs[key] = log
        now = self._clock()
        while log and now >= log[0] + self.window:
            log.popleft()
        return log, now

    def allow(self, key):
        log, now = self._log(key)
        if len(log) < self.limit:
            log.append(now)
            return True
        return False

    def remaining(self, key):
        log, _ = self._log(key)
        return max(0, self.limit - len(log))

    def retry_after(self, key):
        log, now = self._log(key)
        if len(log) < self.limit:
            return 0.0
        return float(log[0] + self.window - now)

    def reset(self, key=None):
        if key is None:
            self._logs.clear()
        else:
            self._logs.pop(key, None)


class TokenBucketLimiter:
    def __init__(self, capacity, refill_rate, clock=time.monotonic):
        if not _is_num(capacity) or capacity <= 0:
            raise ValueError("capacity must be a positive number")
        if not _is_num(refill_rate) or refill_rate <= 0:
            raise ValueError("refill_rate must be a positive number")
        self.capacity = capacity
        self.refill_rate = refill_rate
        self._clock = clock
        self._buckets = {}  # key -> [tokens, last_update]

    def _check_cost(self, tokens):
        if not _is_num(tokens) or tokens <= 0 or tokens > self.capacity:
            raise ValueError("tokens must be in (0, capacity]")

    def _bucket(self, key):
        now = self._clock()
        b = self._buckets.get(key)
        if b is None:
            b = [float(self.capacity), now]
            self._buckets[key] = b
            return b
        elapsed = now - b[1]
        if elapsed > 0:
            b[0] = min(float(self.capacity), b[0] + elapsed * self.refill_rate)
        b[1] = now
        return b

    def allow(self, key, tokens=1):
        self._check_cost(tokens)
        b = self._bucket(key)
        if b[0] >= tokens:
            b[0] -= tokens
            if b[0] < 0:
                b[0] = 0.0
            return True
        return False

    def remaining(self, key):
        return float(self._bucket(key)[0])

    def retry_after(self, key, tokens=1):
        self._check_cost(tokens)
        b = self._bucket(key)
        if b[0] >= tokens:
            return 0.0
        return float((tokens - b[0]) / self.refill_rate)

    def reset(self, key=None):
        if key is None:
            self._buckets.clear()
        else:
            self._buckets.pop(key, None)
