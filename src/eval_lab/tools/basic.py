"""Shell and filesystem tools (spec 12.2)."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

from eval_lab.tools.protocol import SideEffect, ToolContext, ToolResult, register_tool


class ShellTool:
    name: str = "shell"
    side_effect: SideEffect = "workspace"
    input_schema: dict[str, Any] = {
        "type": "object",
        "properties": {"command": {"type": "string"}},
        "required": ["command"],
    }

    def execute(self, args: dict[str, Any], context: ToolContext) -> ToolResult:
        command = args.get("command", "")
        cwd = context.workspace_root
        try:
            proc = subprocess.run(
                command,
                shell=True,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=context.timeout_s,
                env={**os.environ, "PYTHONHASHSEED": "0"},
            )
        except subprocess.TimeoutExpired:
            return ToolResult(ok=False, output="", error="command timed out", truncated=True)
        except Exception as exc:
            return ToolResult(ok=False, output="", error=str(exc))
        combined = (proc.stdout or "") + (proc.stderr or "")
        truncated = len(combined) > context.max_output_chars
        if truncated:
            combined = combined[: context.max_output_chars] + "\n... [truncated]"
        return ToolResult(
            ok=proc.returncode == 0,
            output=combined,
            exit_code=proc.returncode,
            error=None if proc.returncode == 0 else "command returned nonzero",
            truncated=truncated,
        )


class FileReadTool:
    name: str = "file_read"
    side_effect: SideEffect = "none"
    input_schema: dict[str, Any] = {
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
    }

    def execute(self, args: dict[str, Any], context: ToolContext) -> ToolResult:
        raw = args.get("path", "")
        if context.workspace_root:
            p = _resolve_within(raw, Path(context.workspace_root))
        else:
            p = Path(raw)
        if not p.exists() or not p.is_file():
            return ToolResult(ok=False, output="", error=f"file not found: {raw}")
        content = p.read_text(encoding="utf-8", errors="replace")
        truncated = len(content) > context.max_output_chars
        if truncated:
            content = content[: context.max_output_chars] + "\n... [truncated]"
        return ToolResult(ok=True, output=content, truncated=truncated)


class FileWriteTool:
    name: str = "file_write"
    side_effect: SideEffect = "workspace"
    input_schema: dict[str, Any] = {
        "type": "object",
        "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
        "required": ["path", "content"],
    }

    def execute(self, args: dict[str, Any], context: ToolContext) -> ToolResult:
        raw = args.get("path", "")
        content = args.get("content", "")
        if context.workspace_root:
            p = _resolve_within(raw, Path(context.workspace_root))
        else:
            p = Path(raw)
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
        except Exception as exc:
            return ToolResult(ok=False, output="", error=str(exc))
        return ToolResult(ok=True, output=f"wrote {p}")


class ListFilesTool:
    name: str = "list_files"
    side_effect: SideEffect = "none"
    input_schema: dict[str, Any] = {
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": [],
    }

    def execute(self, args: dict[str, Any], context: ToolContext) -> ToolResult:
        base = Path(context.workspace_root) if context.workspace_root else Path.cwd()
        rel = args.get("path", ".")
        p = (base / rel).resolve() if rel != "." else base
        if not p.exists():
            return ToolResult(ok=False, output="", error=f"path not found: {rel}")
        entries = [
            str(x.relative_to(base)) + ("/" if x.is_dir() else "") for x in sorted(p.iterdir())
        ]
        return ToolResult(ok=True, output="\n".join(entries) if entries else "(empty)")


def _resolve_within(raw: str, root: Path) -> Path:
    """Resolve raw path but refuse to escape the workspace root."""
    p = (root / raw).resolve()
    root_resolved = root.resolve()
    if not p.is_relative_to(root_resolved):
        raise ValueError(f"path escapes workspace: {raw}")
    return p


register_tool(ShellTool())
register_tool(FileReadTool())
register_tool(FileWriteTool())
register_tool(ListFilesTool())
