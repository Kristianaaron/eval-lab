"""Process-wide event dispatch (legacy string-keyed API).

Handlers are registered per event *name* and receive the payload dict. The
registry is a module global, which is why ``build_app`` has to ``reset()`` it:
two applications cannot coexist in one process.
"""

from __future__ import annotations

from typing import Callable

Handler = Callable[[dict], None]

_HANDLERS: dict[str, list[Handler]] = {}


def on(name: str, handler: Handler) -> None:
    """Register ``handler`` for the event called ``name``."""
    if not isinstance(name, str) or not name:
        raise TypeError("event name must be a non-empty string")
    handlers = _HANDLERS.setdefault(name, [])
    if handler not in handlers:
        handlers.append(handler)


def off(name: str, handler: Handler) -> None:
    handlers = _HANDLERS.get(name, [])
    if handler in handlers:
        handlers.remove(handler)


def emit(name: str, payload: dict | None = None) -> int:
    """Call every handler registered for ``name``; returns how many ran."""
    if not isinstance(name, str) or not name:
        raise TypeError("event name must be a non-empty string")
    data = dict(payload or {})
    handlers = list(_HANDLERS.get(name, []))
    for handler in handlers:
        handler(data)
    return len(handlers)


def handler_count(name: str) -> int:
    return len(_HANDLERS.get(name, []))


def reset() -> None:
    """Forget every handler (used when a new application is built)."""
    _HANDLERS.clear()
