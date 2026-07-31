"""Agent executor (spec 9.4, 10.3): cycle model -> tool-call -> observation -> model.

No hidden harness assistance (spec 10.4): malformed tool calls are surfaced to
the model as errors rather than silently repaired.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

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


def _tool_for(name: str) -> Tool | None:
    registry: dict[str, Tool] = {
        "shell": ShellTool(),
        "file_read": FileReadTool(),
        "file_write": FileWriteTool(),
        "list_files": ListFilesTool(),
    }
    return registry.get(name)


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
) -> AgentRun:
    """Execute a model-driven tool loop until the model stops or a budget is hit."""
    run = AgentRun()
    ws = sandbox.workspace_path()
    tool_ctx = ToolContext(
        workspace_root=ws,
        timeout_s=min(timeout_s, 30.0),
        trace=trace,
    )
    history: list[str] = []

    for turn_idx in range(max_turns):
        if trace:
            trace.record("agent_turn_start", {"turn": turn_idx})

        # Build the user/assistant context from history (append-only text).
        user_content = prompt
        if history:
            user_content = prompt + "\n\n## Observations so far\n" + "\n\n".join(history[-12:])

        req = GenerationRequest(prompt=user_content, system_prompt=system_prompt, max_tokens=1500)
        result = model.generate(req)
        if result.error:
            run.error = result.error
            run.status = "error"
            return run
        if trace:
            trace.record("model_completion", {"finish_reason": result.finish_reason})

        # If the model produced no tool calls, treat output as final.
        if not result.tool_calls:
            run.final_answer = result.text
            run.status = "completed"
            break

        turn = AgentTurn(model_output=result.text, tool_calls=result.tool_calls)
        for tc in result.tool_calls:
            if len(run.turns) + len(turn.tool_calls) > max_tool_calls:
                run.status = "budget"
                run.error = "max_tool_calls exceeded"
                return run
            obs = _dispatch(tc, tool_ctx, allowed_tools, trace)
            turn.observations.append(obs)
            history.append(
                f"[{tc.name}] args={json.dumps(tc.arguments)} -> {obs.output or obs.error}"
            )
        run.turns.append(turn)

    else:
        run.status = "budget"
        run.error = f"max_turns ({max_turns}) exceeded"

    return run


def _dispatch(
    tc: ToolCall,
    ctx: ToolContext,
    allowed_tools: list[str] | None,
    trace: TraceRecorder | None,
) -> ToolResult:
    if allowed_tools and tc.name not in allowed_tools:
        obs = ToolResult(ok=False, output="", error=f"tool not allowed: {tc.name}")
    else:
        tool = _tool_for(tc.name)
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
                "ok": obs.ok,
                "exit_code": obs.exit_code,
                "truncated": obs.truncated,
                "error": obs.error,
            },
        )
    return obs
