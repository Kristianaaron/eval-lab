"""Next-run computation for simple schedules: ``every <n> <unit>`` and ``daily at HH:MM``."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

from flowkit.errors import ConfigError

_EVERY = re.compile(r"^every\s+(\d+)\s*(s|sec|m|min|h|hour|d|day)s?$")
_DAILY = re.compile(r"^daily\s+at\s+(\d{1,2}):(\d{2})$")
_UNITS = {"s": 1, "sec": 1, "m": 60, "min": 60, "h": 3600, "hour": 3600, "d": 86400, "day": 86400}


def parse_schedule(text: str) -> tuple[str, int]:
    """Return ("interval", seconds) or ("daily", seconds-after-midnight)."""
    t = text.strip().lower()
    m = _EVERY.match(t)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        if n <= 0:
            raise ConfigError("interval must be positive")
        return "interval", n * _UNITS[unit]
    m = _DAILY.match(t)
    if m:
        hh, mm = int(m.group(1)), int(m.group(2))
        if not (0 <= hh < 24 and 0 <= mm < 60):
            raise ConfigError(f"bad time of day in {text!r}")
        return "daily", hh * 3600 + mm * 60
    raise ConfigError(f"cannot parse schedule {text!r}")


def next_run(text: str, now: datetime, last: datetime | None = None) -> datetime:
    kind, seconds = parse_schedule(text)
    now = now.astimezone(UTC)
    if kind == "interval":
        anchor = last.astimezone(UTC) if last else now
        candidate = anchor + timedelta(seconds=seconds)
        while candidate <= now:
            candidate += timedelta(seconds=seconds)
        return candidate
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    candidate = midnight + timedelta(seconds=seconds)
    if candidate <= now:
        candidate += timedelta(days=1)
    return candidate
