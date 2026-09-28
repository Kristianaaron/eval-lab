"""``shop events``: every event name with its number of subscribers."""

from __future__ import annotations

from typing import TextIO

from core import events
from core.constants import ALL_EVENTS


def list_events(app, out: TextIO) -> None:
    for name in ALL_EVENTS:
        out.write(f"{name:<24}{events.handler_count(name):>3}\n")
