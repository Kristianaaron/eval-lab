"""Runner protocol and direct runner (spec 10)."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from eval_lab.adapters.base import GenerationRequest, ModelAdapter
from eval_lab.schemas.models import RunManifest, TaskSpec
from eval_lab.scorers.aggregate import score_oracle
from eval_lab.storage.artifacts import RunWorkspace
from eval_lab.storage.sqlite import RunStore
from eval_lab.traces.recorder import TraceRecorder


@dataclass
class RunContext:
    task: TaskSpec
    model: ModelAdapter
    model_id: str
    harness_id: str | None = None
    seed: int | None = None
    runs_root: str = "runs"
    store: RunStore | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class RunResult:
    run_id: str
    run_dir: str
    output: str
    aggregate: Any
    scores: list[Any]
    manifest: dict[str, object]
    status: str
    duration_s: float
    error: str | None = None


class Runner(Protocol):
    def prepare(self, task: TaskSpec, context: RunContext) -> Any: ...
    def execute(self, prepared: Any) -> Any: ...
    def finalize(self, raw: Any) -> RunResult: ...
    def execute_task(self, task: TaskSpec, context: RunContext) -> RunResult: ...


class DirectRunner:
    """Prompt-in/out evaluation with no tool loop (spec 10.2)."""

    def execute_task(self, task: TaskSpec, context: RunContext) -> RunResult:
        run_id = uuid.uuid4().hex[:12]
        ws = RunWorkspace(context.runs_root, run_id)

        # Load instruction: prefer an explicit prompt in context; else read the
        # task's instruction file text; else fall back to the raw file name.
        prompt = context.extra.get("prompt")
        if prompt is None:
            ifcand = Path(task.input.instruction_file)
            prompt = (
                ifcand.read_text(encoding="utf-8")
                if ifcand.exists()
                else task.input.instruction_file
            )

        recorder = TraceRecorder(run_id, ws.trace_path())
        recorder.record(
            "run_start", {"task_id": task.id, "model_id": context.model_id, "seed": context.seed}
        )

        start = time.monotonic()
        error: str | None = None
        request = self._build_request(prompt, context)
        try:
            recorder.record(
                "model_request", {"prompt_tokens": None, "max_tokens": request.max_tokens}
            )
            result = context.model.generate(request)
            output = result.text
            recorder.record(
                "model_completion",
                {
                    "finish_reason": result.finish_reason,
                    "prompt_tokens": result.prompt_tokens,
                    "completion_tokens": result.completion_tokens,
                    "error": result.error,
                },
            )
            if result.error:
                error = result.error
        except Exception as exc:  # pragma: no cover - defensive
            output = ""
            error = str(exc)
            recorder.record("exception", {"error": error})
        duration = time.monotonic() - start
        recorder.record("run_completion", {"duration_s": duration, "error": error})

        # Score.
        scores = []
        aggregate = None
        if not error:
            aggregate = score_oracle(task, output=output, run_dir=ws.root)
            scores = aggregate.scores
            ws.append_scores([s.model_dump() for s in scores])

        manifest = self._manifest(task, context, run_id, ws, aggregate, duration, error)
        ws.write_manifest(manifest)
        ws.write_result(
            {
                "run_id": run_id,
                "output": output,
                "error": error,
                "aggregate": aggregate.total if aggregate else None,
                "passed": aggregate.passed if aggregate else False,
                "scores": [s.model_dump() for s in scores] if scores else [],
                "duration_s": duration,
            }
        )
        recorder.close()

        # Write the human-readable report so every run directory is self-contained.
        from eval_lab.reports.markdown import write_run_report

        write_run_report(ws.root)

        # Persist index.
        if context.store:
            context.store.insert_run(manifest)
            if scores:
                context.store.insert_scores(run_id, [s.model_dump() for s in scores])
            status = "completed" if aggregate is not None else "error"
            context.store.update_status(
                run_id,
                status,
                aggregate=aggregate.total if aggregate else None,
                passed=aggregate.passed if aggregate else False,
            )

        status = "completed" if (aggregate is not None and not error) else "error"
        return RunResult(
            run_id=run_id,
            run_dir=str(ws.root),
            output=output,
            aggregate=aggregate,
            scores=scores,
            manifest=manifest,
            status=status,
            duration_s=duration,
            error=error,
        )

    def _build_request(self, prompt: str, context: RunContext) -> GenerationRequest:
        settings = context.extra.get("sampling") or {}
        # If an oracle asks for JSON, request structured output from the adapter.
        structured = None
        for ref in context.task.oracle:
            if ref.type == "json_schema":
                structured = ref.config
                break
        return GenerationRequest(
            prompt=prompt,
            system_prompt=context.extra.get("system_prompt"),
            temperature=float(settings.get("temperature", 0.0)),
            max_tokens=int(settings.get("max_tokens", 4096)),
            seed=context.seed,
            structured_schema=structured,
        )

    def _manifest(
        self,
        task: TaskSpec,
        context: RunContext,
        run_id: str,
        ws: RunWorkspace,
        aggregate: Any,
        duration: float,
        error: str | None,
    ) -> dict[str, object]:
        return RunManifest(
            run_id=run_id,
            created_at=datetime.now(UTC),
            task_id=task.id,
            task_version=task.version,
            model_id=context.model_id,
            harness_id=context.harness_id,
            random_seed=context.seed,
            sampling=context.extra.get("sampling") or {},
            budgets={"timeout_seconds": task.execution.timeout_seconds},
            warm_state="model",
            result_status="completed" if (aggregate is not None and not error) else "error",
        ).model_dump(mode="json") | {
            "run_dir": str(ws.root),
            "level": task.level.value,
            "aggregate_score": aggregate.total if aggregate else None,
            "passed": bool(aggregate.passed) if aggregate else False,
            "duration_s": duration,
        }
