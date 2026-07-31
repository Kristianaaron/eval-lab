"""Tool protocol and tool registry (spec 12.2)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

SideEffect = Literal["none", "workspace", "external"]


@dataclass
class ToolResult:
    ok: bool
    output: str = ""
    exit_code: int | None = None
    error: str | None = None
    artifacts: list[str] = field(default_factory=list)
    truncated: bool = False


@dataclass
class ToolContext:
    workspace_root: str | None = None
    timeout_s: float = 30.0
    max_output_chars: int = 8000
    trace: Any = None  # TraceRecorder or None


class Tool(Protocol):
    name: str
    input_schema: dict[str, Any]
    side_effect: SideEffect

    def execute(self, args: dict[str, Any], context: ToolContext) -> ToolResult: ...


_TOOLS: dict[str, Tool] = {}


def register_tool(tool: Tool) -> None:
    _TOOLS[tool.name] = tool


def get_tool(name: str) -> Tool | None:
    return _TOOLS.get(name)


def available_tools() -> list[str]:
    return sorted(_TOOLS)
