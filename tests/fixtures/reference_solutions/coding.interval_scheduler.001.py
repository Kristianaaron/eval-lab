import heapq


def _is_number(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _check_interval(iv):
    try:
        n = len(iv)
    except TypeError:
        raise ValueError(f"interval must be a sequence of two numbers, got {iv!r}")
    if isinstance(iv, (str, bytes)) or n != 2:
        raise ValueError(f"interval must have exactly two bounds, got {iv!r}")
    start, end = iv[0], iv[1]
    if not _is_number(start) or not _is_number(end):
        raise ValueError(f"interval bounds must be numbers, got {iv!r}")
    if not start < end:
        raise ValueError(f"interval start must be < end, got {iv!r}")
    return (start, end)


def _check_all(intervals):
    if isinstance(intervals, (str, bytes)) or not hasattr(intervals, "__iter__"):
        raise ValueError("expected a sequence of intervals")
    return [_check_interval(iv) for iv in intervals]


def merge_intervals(intervals):
    items = sorted(_check_all(intervals))
    merged = []
    for start, end in items:
        if merged and start <= merged[-1][1]:
            if end > merged[-1][1]:
                merged[-1] = (merged[-1][0], end)
        else:
            merged.append((start, end))
    return merged


def max_concurrent(intervals):
    items = _check_all(intervals)
    if not items:
        return 0
    # Ends sort before starts at the same coordinate (half-open intervals).
    events = []
    for start, end in items:
        events.append((start, 1))
        events.append((end, 0))
    events.sort()
    best = current = 0
    for _, kind in events:
        if kind == 1:
            current += 1
            if current > best:
                best = current
        else:
            current -= 1
    return best


def free_slots(busy, window):
    w_start, w_end = _check_interval(window)
    merged = merge_intervals(busy)
    slots = []
    cursor = w_start
    for start, end in merged:
        if end <= cursor:
            continue
        if start >= w_end:
            break
        if start > cursor:
            slots.append((cursor, start))
        if end > cursor:
            cursor = end
        if cursor >= w_end:
            break
    if cursor < w_end:
        slots.append((cursor, w_end))
    return slots


def schedule(meetings):
    items = _check_all(meetings)
    order = sorted(range(len(items)), key=lambda i: (items[i][0], items[i][1], i))
    rooms = [0] * len(items)
    busy = []  # heap of (end, room)
    free = []  # heap of room indices
    opened = 0
    for i in order:
        start, end = items[i]
        while busy and busy[0][0] <= start:
            _, room = heapq.heappop(busy)
            heapq.heappush(free, room)
        if free:
            room = heapq.heappop(free)
        else:
            room = opened
            opened += 1
        rooms[i] = room
        heapq.heappush(busy, (end, room))
    return rooms
