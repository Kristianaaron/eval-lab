"""Performance runner: streaming timing + telemetry sampling (spec 15).

Executes a direct task through a streaming adapter while (a) recording cold/warm
run markers, (b) emitting a raw ``token_event`` timestamp per token, and (c)
sampling system/NVIDIA/NVMe/network collectors on an interval. On completion it
recomputes TTFT and decode throughput from the raw trace timestamps and persists
per-node telemetry correlation on the manifest (Phase 3 exit gate).
"""

from __future__ import annotations

import socket
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from eval_lab.adapters.base import GenerationRequest, StreamingModelAdapter
from eval_lab.reports.markdown import write_run_report
from eval_lab.runners.direct import RunContext, RunResult
from eval_lab.schemas.models import RunManifest, TaskSpec
from eval_lab.scorers.aggregate import score_oracle
from eval_lab.storage.artifacts import RunWorkspace
from eval_lab.telemetry.correlation import correlate, parse_events, verify_timing
from eval_lab.telemetry.sampler import TelemetrySampler, attach_to_recorder
from eval_lab.traces.recorder import TraceRecorder


class PerfRunner:
    """Execute a direct task under telemetry with streaming-token timing."""

    def __init__(
        self,
        *,
        interval_s: float = 0.05,
        node_id: str | None = None,
        cold_start: bool = False,
        warm_state: str = "warm",
        telemetry: bool = True,
    ) -> None:
        self.interval_s = interval_s
        self.node_id = node_id
        self.cold_start = cold_start
        self.warm_state = warm_state
        self.telemetry_enabled = telemetry

    def execute_task(self, task: TaskSpec, context: RunContext) -> RunResult:
        run_id = uuid.uuid4().hex[:12]
        ws = RunWorkspace(context.runs_root, run_id)
        recorder = TraceRecorder(run_id, ws.trace_path())
        node_id = self.node_id or context.extra.get("node_id") or str(socket.gethostname())

        prompt = context.extra.get("prompt")
        if prompt is None:
            ifcand = Path(task.input.instruction_file)
            prompt = (
                ifcand.read_text(encoding="utf-8")
                if ifcand.exists()
                else task.input.instruction_file
            )

        recorder.record(
            "telemetry_marker",
            {
                "phase": "run_start",
                "warm_state": self.warm_state,
                "cold_start": self.cold_start,
                "node_id": node_id,
            },
        )

        sampler = None
        if self.telemetry_enabled:
            sampler = TelemetrySampler(interval_s=self.interval_s, node_id=node_id)
            attach_to_recorder(sampler, recorder)

        start = time.monotonic()
        error: str | None = None
        output = ""
        request = self._build_request(prompt, context)
        try:
            recorder.record(
                "model_request", {"prompt_tokens": None, "max_tokens": request.max_tokens}
            )
            if isinstance(context.model, StreamingModelAdapter):
                result = context.model.generate_stream(
                    request,
                    lambda text, wall_s: recorder.record(
                        "token_event", {"wall_time_ns": int(wall_s * 1e9), "token_len": len(text)}
                    ),
                )
            else:
                result = context.model.generate(request)
            output = result.text
            timing = result.timing
            recorder.record(
                "model_completion",
                {
                    "finish_reason": result.finish_reason,
                    "prompt_tokens": result.prompt_tokens,
                    "completion_tokens": result.completion_tokens,
                    "ttft_s": timing.ttft_s if timing else None,
                    "decode_duration_s": timing.decode_duration_s if timing else None,
                    "decode_tokens_per_s": timing.decode_tokens_per_s if timing else None,
                    "error": result.error,
                },
            )
            if result.error:
                error = result.error
        except Exception as exc:  # pragma: no cover - defensive
            output = ""
            error = str(exc)
            recorder.record("exception", {"error": error})

        if sampler:
            sampler.stop()
        duration = time.monotonic() - start
        recorder.record("run_completion", {"duration_s": duration, "error": error})

        # Verify timing against raw timestamps + per-node correlation.
        events = parse_events(ws.trace_path())
        timing_verified = verify_timing(events)
        per_node = correlate(events)
        recorder.record(
            "telemetry_correlation",
            {"timing": timing_verified, "per_node": per_node},
        )
        recorder.close()

        # Score.
        scores = []
        aggregate = None
        if not error:
            aggregate = score_oracle(task, output=output, run_dir=ws.root)
            scores = aggregate.scores
            ws.append_scores([s.model_dump() for s in scores])

        summary = sampler.summary() if sampler else {}
        manifest = self._manifest(
            task,
            context,
            run_id,
            ws,
            aggregate,
            duration,
            error,
            node_id,
            timing_verified,
            per_node,
            summary,
        )
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
                "timing": timing_verified,
                "per_node": per_node,
            }
        )
        write_run_report(ws.root)

        if context.store:
            context.store.insert_run(manifest)
            if scores:
                context.store.insert_scores(run_id, [s.model_dump() for s in scores])
            context.store.update_status(
                run_id,
                "completed" if aggregate is not None else "error",
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
        node_id: str,
        timing_verified: dict[str, Any],
        per_node: dict[str, Any],
        summary: dict[str, Any],
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
            warm_state=self.warm_state,
            telemetry_stream=str(ws.trace_path()),
            timing=timing_verified,
            result_status="completed" if (aggregate is not None and not error) else "error",
        ).model_dump(mode="json") | {
            "run_dir": str(ws.root),
            "level": task.level.value,
            "aggregate_score": aggregate.total if aggregate else None,
            "passed": bool(aggregate.passed) if aggregate else False,
            "duration_s": duration,
            "node_id": node_id,
            "telemetry": {
                "per_node": per_node,
                "summary": summary,
            },
        }
