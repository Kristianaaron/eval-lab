Implement a set of utilities for **half-open** numeric intervals `[start, end)`. Only the standard library may be used.

## Interval representation and validation

An interval is any sequence of exactly two numbers `(start, end)` where each bound is an `int` or `float` (a `bool` is **not** a number) and `start < end`. Every function below must validate every interval it receives and raise `ValueError` for anything else: wrong length, non-numeric bounds, `start >= end` (empty intervals are rejected), or an input that is not a sequence of intervals. Do not mutate the inputs. Inputs are not necessarily sorted and may contain duplicates. All returned intervals are `tuple`s of two numbers, and a returned bound keeps the type (`int`/`float`) of the input bound it came from.

## Required functions

```
def merge_intervals(intervals) -> list[tuple]: ...
def max_concurrent(intervals) -> int: ...
def free_slots(busy, window) -> list[tuple]: ...
def schedule(meetings) -> list[int]: ...
```

- `merge_intervals(intervals)`: return the minimal list of disjoint intervals covering exactly the same points, sorted by start. Overlapping **and touching** intervals merge: `[1, 3)` and `[3, 5)` become `(1, 5)`. An empty input returns `[]`.
- `max_concurrent(intervals)`: the largest number of intervals that contain a common point. Because intervals are half-open, `[1, 3)` and `[3, 5)` do not overlap, so their concurrency is `1`. Empty input returns `0`.
- `free_slots(busy, window)`: `window` is a single interval. Return the maximal sub-intervals of `window` not covered by any interval in `busy`, sorted by start. Busy intervals may lie partly or entirely outside the window; only the part inside the window matters. Never return an empty interval. If nothing is busy inside the window, return `[window]` as a tuple.
- `schedule(meetings)`: assign each meeting to a room so that no two meetings in the same room overlap (touching is allowed) using the **minimum possible number of rooms**. Return a list `rooms` with `rooms[i]` being the room index (an `int` starting at `0`) of `meetings[i]`. The assignment must be exactly this deterministic procedure: consider meetings in ascending order of `(start, end, original index)`; for each meeting, a room is *free* when its most recently assigned meeting ends at or before this meeting's start; assign the free room with the **lowest index**; if no room is free, open a new room with index equal to the number of rooms opened so far. The number of rooms used therefore equals `max_concurrent(meetings)`. Empty input returns `[]`.

All functions must run in O(n log n) time (or better) in the number of intervals: 50,000 intervals must be processed well within a second per call.

Reply with exactly one fenced ```python block containing a complete module that defines these names. Do not include tests or example usage outside the block.
