"""Context-pressure runner (spec 10.3).

Pre-fills a configurable fraction of the model context window with filler
tokens, then runs a direct task against the remainder.  Mirrors the
tool-eval-bench ``--context-pressure 0.75`` idea: measure whether the model
behaves correctly when the window is already partly consumed.

Only depends on the model adapter's ``generate`` and the shared
``GenerationRequest``; no extra infrastructure.
"""

from __future__ import annotations

import math
import time
import uuid
from pathlib import Path
from typing import Any

from eval_lab.adapters.base import GenerationRequest, ModelAdapter
from eval_lab.runners.direct import RunContext, RunResult, DirectRunner
from eval_lab.schemas.models import TaskSpec
from eval_lab.scorers.aggregate import score_oracle
from eval_lab.storage.artifacts import RunWorkspace
from eval_lab.traces.recorder import TraceRecorder


class ContextPressureRunner(DirectRunner):
    """Direct runner that pre-fills context before the eval task."""

    def __init__(self, fill_fraction: float = 0.75) -> None:
        if not math.isfinite(fill_fraction) or not (0.0 <= fill_fraction < 1.0):
            raise ValueError("fill_fraction must be in [0, 1)")
        self.fill_fraction = fill_fraction

    def execute_task(self, task: TaskSpec, context: RunContext) -> RunResult:
        run_id = uuid.uuid4().hex[:12]
        ws = RunWorkspace(context.runs_root, run_id)
        recorder = TraceRecorder(run_id, ws.trace_path())
        recorder.record("run_start", {"task_id": task.id, "fill_fraction": self.fill_fraction})
        start = time.monotonic()
        output = ""
        error = None
        try:
            prompt = context.extra.get("prompt")
            if prompt is None:
                ifcand = Path(task.input.instruction_file)
                prompt = ifcand.read_text(encoding="utf-8")

            # Estimate the context budget from the model's reported prompt tokens.
            warmup = GenerationRequest(prompt="x", max_tokens=1)
            probe = context.model.generate(warmup)
            prompt_budget = probe.prompt_tokens or 0
            if prompt_budget <= 0:
                prompt_budget = 4096

            # Build the filler: repeat a known-safe sentence to consume budget.
            fill_tokens = int(prompt_budget * self.fill_fraction)
            filler = (
                "The quick brown fox jumps over the lazy dog. "
                "This is a synthetic context filler used to pressure the window. "
            )
            # Approximate token count by character length (4 chars per token).
            filler = filler * max(1, fill_tokens * 4 // len(filler))
            context.extra["prompt"] = filler + "\n\n" + prompt

            request = GenerationRequest(
                prompt=context.extra["prompt"],
                system_prompt=context.extra.get("system_prompt"),
                temperature=float(context.sampling.get("temperature", 0.0)),
                max_tokens=int(context.sampling.get("max_tokens", 256)),
                timeout_seconds=context.http_timeout_seconds,
                logprobs=True,
            )
            recorder.record("model_request", {"prompt_tokens": None, "max_tokens": request.max_tokens})
            result = context.model.generate(request)
            output = result.text
            recorder.record("model_completion", {"finish_reason": result.finish_reason, "prompt_tokens": result.prompt_tokens})
            if result.error:
                error = result.error
        except Exception as exc:  # pragma: no cover - defensive
            output = ""
            error = str(exc)
            recorder.record("exception", {"error": error})
        duration = time.monotonic() - start

        aggregate = score_oracle(task, output, run_dir=ws.run_dir(), logprobs=result.logprobs if "result" in dir() else None)
        recorder.record("aggregate", {"total": aggregate.total, "passed": aggregate.passed})
        recorder.finalize()

        manifest = {
            "run_id": run_id,
            "task_id": task.id,
            "fill_fraction": self.fill_fraction,
            "prompt_budget_est": prompt_budget if "prompt_budget" in dir() else None,
            "output": output,
            "error": error,
            "duration_s": duration,
        }
        return RunResult(
            run_id=run_id,
            run_dir=str(ws.run_dir()),
            output=output,
            aggregate=aggregate,
            scores=list(aggregate.scores),
            manifest=manifest,
            status="ok" if not error else "error",
            duration_s=duration,
            error=error,
        )