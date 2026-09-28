"""A small RFC-4180-ish CSV reader: quoted fields, doubled quotes, CRLF."""

from __future__ import annotations

from collections.abc import Iterable, Iterator

from flowkit.errors import ParseError
from flowkit.records import Record, parse_timestamp


def split_row(line: str, delimiter: str = ",") -> list[str]:
    fields: list[str] = []
    buf: list[str] = []
    in_quotes = False
    i = 0
    while i < len(line):
        ch = line[i]
        if in_quotes:
            if ch == '"':
                if i + 1 < len(line) and line[i + 1] == '"':
                    buf.append('"')
                    i += 1
                else:
                    in_quotes = False
            else:
                buf.append(ch)
        elif ch == '"':
            in_quotes = True
        elif ch == delimiter:
            fields.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
        i += 1
    if in_quotes:
        raise ParseError("unterminated quoted field")
    fields.append("".join(buf))
    return fields


def parse_csv(
    lines: Iterable[str],
    *,
    delimiter: str = ",",
    timestamp_field: str | None = None,
    source: str = "csv",
) -> Iterator[Record]:
    header: list[str] | None = None
    for n, raw in enumerate(lines, start=1):
        line = raw.rstrip("\r\n")
        if not line.strip():
            continue
        try:
            cells = split_row(line, delimiter)
        except ParseError as exc:
            raise ParseError(str(exc), n) from None
        if header is None:
            header = [c.strip() for c in cells]
            if len(set(header)) != len(header):
                raise ParseError("duplicate column names", n)
            continue
        if len(cells) != len(header):
            raise ParseError(f"expected {len(header)} fields, got {len(cells)}", n)
        fields = dict(zip(header, cells, strict=True))
        ts = parse_timestamp(fields[timestamp_field]) if timestamp_field else None
        yield Record(fields, ts, source)
