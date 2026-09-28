"""Record validation rules: declarative checks that return structured problems."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from flowkit.records import Record

Check = Callable[[Record], str | None]


@dataclass(frozen=True)
class Problem:
    index: int
    field: str
    message: str


def required(*names: str) -> Check:
    def check(record: Record) -> str | None:
        missing = [n for n in names if n not in record.fields or record[n] in ("", None)]
        return f"missing {', '.join(missing)}" if missing else None

    return check


def matches(field: str, pattern: str) -> Check:
    regex = re.compile(pattern)

    def check(record: Record) -> str | None:
        value = record.fields.get(field)
        if value is None or regex.fullmatch(str(value)):
            return None
        return f"{field}={value!r} does not match {pattern}"

    return check


def in_range(field: str, low: float, high: float) -> Check:
    def check(record: Record) -> str | None:
        value = record.fields.get(field)
        if value is None:
            return None
        try:
            number = float(value)
        except (TypeError, ValueError):
            return f"{field}={value!r} is not numeric"
        if not low <= number <= high:
            return f"{field}={number} outside [{low}, {high}]"
        return None

    return check


def one_of(field: str, allowed: Iterable[Any]) -> Check:
    choices = set(allowed)

    def check(record: Record) -> str | None:
        value = record.fields.get(field)
        if value is None or value in choices:
            return None
        return f"{field}={value!r} not in {sorted(map(str, choices))}"

    return check


def validate(records: Iterable[Record], checks: Iterable[Check]) -> list[Problem]:
    problems: list[Problem] = []
    checks = list(checks)
    for i, record in enumerate(records):
        for check in checks:
            message = check(record)
            if message:
                field = message.split("=", 1)[0].split(" ", 1)[-1] if "=" in message else "*"
                problems.append(Problem(i, field, message))
    return problems


def partition(records: Iterable[Record], checks: Iterable[Check]) -> tuple[list[Record], list[Record]]:
    """Split into (valid, invalid) preserving order."""
    checks = list(checks)
    good: list[Record] = []
    bad: list[Record] = []
    for record in records:
        if any(check(record) for check in checks):
            bad.append(record)
        else:
            good.append(record)
    return good, bad
