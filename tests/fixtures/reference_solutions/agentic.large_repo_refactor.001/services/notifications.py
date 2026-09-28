"""Outbound notifications (collected in an outbox instead of being sent)."""

from __future__ import annotations

from core.events import Event, EventType
from core.constants import NOTIFICATION_CHANNELS
from core.errors import ValidationError


class NotificationService:
    def __init__(self, bus) -> None:
        self.bus = bus
        self.outbox: list[tuple[str, str, str]] = []

    def send(self, channel: str, recipient: str, message: str) -> int:
        if channel not in NOTIFICATION_CHANNELS:
            raise ValidationError(f"unknown channel: {channel}")
        self.outbox.append((channel, recipient, message))
        self.bus.publish(Event(EventType.NOTIFICATION_SENT, {"channel": channel, "recipient": recipient, "message": message}))
        return len(self.outbox)

    def sent_via(self, channel: str) -> list[str]:
        return [message for ch, _, message in self.outbox if ch == channel]
