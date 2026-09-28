"""Exception hierarchy shared by every flowkit module."""

from __future__ import annotations


class FlowkitError(Exception):
    """Base class; every error raised on purpose derives from it."""


class ConfigError(FlowkitError):
    """A configuration string could not be parsed or is incomplete."""


class ParseError(FlowkitError):
    """Input text is malformed. Carries the 1-based line number."""

    def __init__(self, message: str, line_no: int | None = None) -> None:
        self.line_no = line_no
        prefix = f"line {line_no}: " if line_no is not None else ""
        super().__init__(prefix + message)


class SchemaError(FlowkitError):
    """A record does not satisfy a transform's expectations."""
