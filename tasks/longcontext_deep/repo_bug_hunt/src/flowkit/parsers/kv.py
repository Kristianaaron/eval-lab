"""Parse ``key=value key2="quoted value"`` lines into records."""

from __future__ import annotations

import shlex
from collections.abc import Iterable, Iterator

from flowkit.errors import ParseError
from flowkit.records import Record, parse_timestamp


def parse_kv_line(line: str) -> dict[str, str]:
    try:
        tokens = shlex.split(line, posix=True)
    except ValueError as exc:
        raise ParseError(f"bad quoting: {exc}") from None
    out: dict[str, str] = {}
    for tok in tokens:
        if "=" not in tok:
            raise ParseError(f"token without '=': {tok!r}")
        key, _, value = tok.partition("=")
        if not key:
            raise ParseError("empty key")
        out[key] = value
    return out


def parse_kv_lines(
    lines: Iterable[str], *, timestamp_field: str = "ts", source: str = "kv"
) -> Iterator[Record]:
    for n, raw in enumerate(lines, start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            fields = parse_kv_line(line)
        except ParseError as exc:
            raise ParseError(str(exc), n) from None
        ts = parse_timestamp(fields[timestamp_field]) if timestamp_field in fields else None
        yield Record(fields, ts, source)
