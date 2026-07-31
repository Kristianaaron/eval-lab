"""A scripted tool-calling adapter for deterministic agent-loop tests.

The model replies are driven by a user-supplied script of steps. Each step is
either a tool call the model should emit or a final text answer. This lets the
agent executor and Phase 2 integration tests run without a real model.
"""

from __future__ import annotations

from typing import Any

from eval_lab.adapters.base import (
    GenerationRequest,
    GenerationResult,
    HealthStatus,
    ModelAdapter,
    ModelMetadata,
    ToolCall,
)


class ScriptedToolAdapter(ModelAdapter):
    """Adapter that replays a fixed script of tool calls then a final answer.

    ``script`` is a list where each element is either:
      {"tool": name, "args": {...}, "id": optional}
      {"answer": text}
    Each worker step advances the internal script cursor. This adapter is
    deterministic and ignores the actual prompt content.
    """

    def __init__(self, script: list[dict[str, Any]]) -> None:
        self.script = script
        self._cursor = 0

    def healthcheck(self) -> HealthStatus:
        return HealthStatus(ok=True, detail="scripted")

    def metadata(self) -> ModelMetadata:
        return ModelMetadata(
            provider_type="mock-scripted",
            model_name="mock-scripted-v1",
            supports_tools=True,
        )

    def generate(self, request: GenerationRequest) -> GenerationResult:
        if self._cursor >= len(self.script):
            return GenerationResult(text="[no more steps]", finish_reason="stop")
        step = self.script[self._cursor]
        self._cursor += 1
        if "answer" in step:
            return GenerationResult(text=str(step["answer"]), finish_reason="stop")
        tool = ToolCall(
            id=step.get("id", f"tc-{self._cursor}"),
            name=str(step["tool"]),
            arguments=step.get("args", {}),
        )
        return GenerationResult(
            text="[tool call]",
            finish_reason="tool_calls",
            tool_calls=[tool],
        )
