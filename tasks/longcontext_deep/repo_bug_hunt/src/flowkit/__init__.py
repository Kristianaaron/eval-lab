"""flowkit — tiny batch record pipeline toolkit (see README.md)."""

from flowkit.errors import ConfigError, FlowkitError, ParseError
from flowkit.records import Record

__all__ = ["ConfigError", "FlowkitError", "ParseError", "Record"]
__version__ = "1.4.2"
