"""Agent executor (spec 9.4, 10.3): cycle model -> tool-call -> observation -> model.

The model receives the tool definitions natively (OpenAI ``tools`` schema) and a
real multi-turn message history: assistant tool-call messages followed by one
``tool`` message per call carrying the observation. No hidden harness
assistance (spec 10.4): malformed or disallowed tool calls are surfaced to the
model as tool errors rather than silently repaired.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

from eval_lab.adapters.base import GenerationRequest, ModelAdapter, ToolCall
from eval_lab.sandboxes.base import Sandbox
from eval_lab.tools.basic import (
    FileReadTool,
    FileWriteTool,
    ListFilesTool,
    ShellTool,
)
from eval_lab.tools.protocol import Tool, ToolContext, ToolResult
from eval_lab.traces.recorder import TraceRecorder

DEFAULT_SYSTEM_PROMPT = (
    "You are an autonomous software engineering agent working inside an isolated "
    "workspace. Use the provided tools to inspect files, edit code and run "
    "commands. Verify your work by running the tests or commands the task names. "
    "When the task is complete, reply with a short final summary and no tool calls."
)

TOOL_DESCRIPTIONS = {
    "shell": "Run a shell command in the workspace root and return its combined output.",
    "file_read": "Read a UTF-8 text file (path relative to the workspace root).",
    "file_write": "Create or overwrite a text file (path relative to the workspace root).",
    "list_files": "List entries of a directory (path relative to the workspace root).",
}


@dataclass
class AgentTurn:
    model_output: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    observations: list[ToolResult] = field(default_factory=list)


@dataclass
class AgentRun:
    turns: list[AgentTurn] = field(default_factory=list)
    final_answer: str = ""
    error: str | None = None
    status: str = "completed"  # completed | timeout | budget | error | safety
    messages: list[dict[str, Any]] = field(default_factory=list)
    tool_call_count: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0


def _registry() -> dict[str, Tool]:
    return {
        "shell": ShellTool(),
        "file_read": FileReadTool(),
        "file_write": FileWriteTool(),
        "list_files": ListFilesTool(),
    }


def tool_definitions(allowed: list[str] | None = None) -> list[dict[str, Any]]:
    """OpenAI-style function definitions for the harness tools."""
    defs: list[dict[str, Any]] = []
    for name, tool in _registry().items():
        if allowed and name not in allowed:
            continue
        defs.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": TOOL_DESCRIPTIONS.get(name, name),
                    "parameters": tool.input_schema,
                },
            }
        )
    return defs


def run_agent(
    model: ModelAdapter,
    *,
    prompt: str,
    system_prompt: str | None,
    sandbox: Sandbox,
    trace: TraceRecorder | None = None,
    timeout_s: float = 120.0,
    max_turns: int = 30,
    max_tool_calls: int = 120,
    allowed_tools: list[str] | None = None,
    max_tokens: int = 4096,
    temperature: float = 0.0,
    seed: int | None = None,
) -> AgentRun:
    """Execute a model-driven tool loop until the model stops or a budget is hit."""
    run = AgentRun()
    ws = sandbox.workspace_path()
    tool_ctx = ToolContext(
        workspace_root=ws,
        timeout_s=min(timeout_s, 120.0),
        trace=trace,
    )
    tools = tool_definitions(allowed_tools)
    messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
    run.messages = messages
    started = time.monotonic()

    for turn_idx in range(max_turns):
        if time.monotonic() - started > timeout_s:
            run.status = "timeout"
            run.error = f"timeout after {timeout_s:.0f}s"
            return run
        if trace:
            trace.record("agent_turn_start", {"turn": turn_idx})

        req = GenerationRequest(
            prompt=prompt,
            system_prompt=system_prompt or DEFAULT_SYSTEM_PROMPT,
            messages=messages,
            tools=tools,
            max_tokens=max_tokens,
            temperature=temperature,
            seed=seed,
        )
        result = model.generate(req)
        run.prompt_tokens += int(result.prompt_tokens or 0)
        run.completion_tokens += int(result.completion_tokens or 0)
        if result.error:
            run.error = result.error
            run.status = "error"
            return run
        if trace:
            trace.record(
                "model_completion",
                {
                    "finish_reason": result.finish_reason,
                    "tool_calls": len(result.tool_calls),
                    "prompt_tokens": result.prompt_tokens,
                    "completion_tokens": result.completion_tokens,
                },
            )

        # If the model produced no tool calls, treat output as final.
        if not result.tool_calls:
            run.final_answer = result.text
            run.status = "completed"
            messages.append({"role": "assistant", "content": result.text})
            break

        if run.tool_call_count + len(result.tool_calls) > max_tool_calls:
            run.status = "budget"
            run.error = "max_tool_calls exceeded"
            return run

        turn = AgentTurn(model_output=result.text, tool_calls=result.tool_calls)
        messages.append(
            {
                "role": "assistant",
                "content": result.text or None,
                "tool_calls": [
                    {
                        "id": tc.id or f"call_{turn_idx}_{i}",
                        "type": "function",
                        "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)},
                    }
                    for i, tc in enumerate(result.tool_calls)
                ],
            }
        )
        for i, tc in enumerate(result.tool_calls):
            obs = _dispatch(tc, tool_ctx, allowed_tools, trace)
            run.tool_call_count += 1
            turn.observations.append(obs)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id or f"call_{turn_idx}_{i}",
                    "name": tc.name,
                    "content": _observation_text(obs),
                }
            )
        run.turns.append(turn)

    else:
        run.status = "budget"
        run.error = f"max_turns ({max_turns}) exceeded"

    return run


def _observation_text(obs: ToolResult) -> str:
    parts: list[str] = []
    if obs.output:
        parts.append(obs.output)
    if obs.error:
        parts.append(f"[error] {obs.error}")
    if obs.exit_code is not None:
        parts.append(f"[exit_code={obs.exit_code}]")
    return "\n".join(parts) if parts else "(no output)"


def _dispatch(
    tc: ToolCall,
    ctx: ToolContext,
    allowed_tools: list[str] | None,
    trace: TraceRecorder | None,
) -> ToolResult:
    if allowed_tools and tc.name not in allowed_tools:
        obs = ToolResult(ok=False, output="", error=f"tool not allowed: {tc.name}")
    else:
        tool = _registry().get(tc.name)
        if tool is None:
            obs = ToolResult(ok=False, output="", error=f"unknown tool: {tc.name}")
        else:
            try:
                obs = tool.execute(tc.arguments, ctx)
            except Exception as exc:
                obs = ToolResult(ok=False, output="", error=f"tool error: {exc}")
    if trace:
        trace.record(
            "tool_result",
            {
                "tool": tc.name,
                "arguments": tc.arguments,
                "ok": obs.ok,
                "exit_code": obs.exit_code,
                "truncated": obs.truncated,
                "error": obs.error,
                "output_head": (obs.output or "")[:400],
            },
        )
    return obs
