"""Helpers shared by the service, repository and CLI layers."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Sequence, TypeVar

from inventory.errors import ValidationError
from inventory.models import Page

T = TypeVar("T")

UTC = timezone.utc


def parse_timestamp(value: str) -> datetime:
    """Parse an ISO-8601 timestamp into an aware UTC datetime.

    A trailing ``Z`` is accepted as UTC. Timestamps that carry an explicit
    offset are converted to UTC; naive timestamps are interpreted as UTC.
    """
    text = value.strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValidationError(f"invalid timestamp: {value!r}") from exc
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def format_timestamp(value: datetime) -> str:
    """Render an aware datetime as ``YYYY-MM-DDTHH:MM:SSZ`` in UTC."""
    if value.tzinfo is None:
        raise ValidationError("cannot format a naive datetime")
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def paginate(items: Sequence[T], page: int, page_size: int) -> Page[T]:
    """Slice ``items`` into the requested 1-based page."""
    if page < 1:
        raise ValidationError("page must be >= 1")
    if page_size < 1:
        raise ValidationError("page_size must be >= 1")
    start = (page - 1) * page_size
    end = start + page_size
    return Page(items=tuple(items[start:end]), page=page, page_size=page_size, total=len(items))


def format_money(amount: Decimal, currency: str = "USD") -> str:
    """``1234.5`` -> ``'1,234.50 USD'``."""
    return f"{amount:,.2f} {currency}"


def normalise_sku(sku: str) -> str:
    cleaned = sku.strip().upper()
    if not cleaned:
        raise ValidationError("sku must not be empty")
    return cleaned
