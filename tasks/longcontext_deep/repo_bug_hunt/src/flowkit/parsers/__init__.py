"""Text parsers producing Record streams."""

from flowkit.parsers.csvlite import parse_csv
from flowkit.parsers.kv import parse_kv_lines

__all__ = ["parse_csv", "parse_kv_lines"]
