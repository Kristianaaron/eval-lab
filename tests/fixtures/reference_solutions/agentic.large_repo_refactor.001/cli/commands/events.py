"""``shop events``: every event name with its number of subscribers."""

from __future__ import annotations

from typing import TextIO

from core.events import EventType


def list_events(app, out: TextIO) -> None:
    for event_type in EventType:
        out.write(f"{event_type.value:<24}{len(app.bus.handlers(event_type)):>3}\n")
