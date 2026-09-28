"""INI-style configuration with ``${NAME}`` environment interpolation.

Format::

    [section]
    key = value           ; comments start with ';' or '#'
    path = ${HOME}/data   ; interpolated from the environment mapping

Section and key names are case-insensitive and stored lower-case.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from flowkit.errors import ConfigError

_SECTION = re.compile(r"^\[([A-Za-z0-9_.-]+)\]$")
_PAIR = re.compile(r"^([A-Za-z0-9_.-]+)\s*=\s*(.*)$")
_VAR = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


class Config:
    def __init__(self, sections: dict[str, dict[str, str]]) -> None:
        self._sections = sections

    def get(self, section: str, key: str, default: str | None = None) -> str | None:
        return self._sections.get(section.lower(), {}).get(key.lower(), default)

    def require(self, section: str, key: str) -> str:
        value = self.get(section, key)
        if value is None:
            raise ConfigError(f"missing required setting {section}.{key}")
        return value

    def getint(self, section: str, key: str, default: int | None = None) -> int | None:
        raw = self.get(section, key)
        if raw is None:
            return default
        try:
            return int(raw)
        except ValueError as exc:
            raise ConfigError(f"{section}.{key} is not an integer: {raw!r}") from exc

    def getbool(self, section: str, key: str, default: bool = False) -> bool:
        raw = self.get(section, key)
        if raw is None:
            return default
        lowered = raw.strip().lower()
        if lowered in ("1", "true", "yes", "on"):
            return True
        if lowered in ("0", "false", "no", "off"):
            return False
        raise ConfigError(f"{section}.{key} is not a boolean: {raw!r}")

    def sections(self) -> list[str]:
        return sorted(self._sections)

    def as_dict(self) -> dict[str, dict[str, str]]:
        return {s: dict(kv) for s, kv in self._sections.items()}


def _strip_comment(line: str) -> str:
    in_quotes = False
    for i, ch in enumerate(line):
        if ch == '"':
            in_quotes = not in_quotes
        elif ch in ";#" and not in_quotes:
            return line[:i]
    return line


def interpolate(value: str, env: Mapping[str, str]) -> str:
    def repl(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in env:
            raise ConfigError(f"undefined variable ${{{name}}}")
        return env[name]

    return _VAR.sub(repl, value)


def parse_config(text: str, env: Mapping[str, str] | None = None) -> Config:
    env = env or {}
    sections: dict[str, dict[str, str]] = {}
    current: str | None = None
    for n, raw in enumerate(text.splitlines(), start=1):
        line = _strip_comment(raw).strip()
        if not line:
            continue
        m = _SECTION.match(line)
        if m:
            current = m.group(1).lower()
            sections.setdefault(current, {})
            continue
        m = _PAIR.match(line)
        if not m:
            raise ConfigError(f"line {n}: cannot parse {raw!r}")
        if current is None:
            raise ConfigError(f"line {n}: key outside of a section")
        key, value = m.group(1).lower(), m.group(2).strip()
        if len(value) >= 2 and value[0] == value[-1] == '"':
            value = value[1:-1]
        sections[current][key] = interpolate(value, env)
    return Config(sections)
