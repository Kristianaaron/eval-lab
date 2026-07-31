"""AgentRunner facade: execute a system-level TaskSpec through the agent loop.

Wires sandbox + agent executor + trace + workspace hashing + budgets + scoring
into a RunResult matching the Executor protocol (execute_task), so the CLI and
batch/suite runners handle agent tasks uniformly with direct tasks.
"""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from eval_lab.reports.markdown import write_run_report
from eval_lab.runners.agent import AgentRun, run_agent
from eval_lab.runners.direct import RunContext, RunResult
from eval_lab.sandboxes.base import build_sandbox
from eval_lab.schemas.models import RunManifest, TaskSpec
from eval_lab.scorers.aggregate import AggregateScore, score_oracle
from eval_lab.storage.artifacts import RunWorkspace, fingerprint_dir
from eval_lab.traces.recorder import TraceRecorder


class AgentRunner:
    """Executes tasks whose ``execution.runner == 'agent'``."""

    def execute_task(self, task: TaskSpec, context: RunContext) -> RunResult:
        run_id = uuid.uuid4().hex[:12]
        ws = RunWorkspace(context.runs_root, run_id)
        recorder = TraceRecorder(run_id, ws.trace_path())
        recorder.record(
            "run_start",
            {"task_id": task.id, "model_id": context.model_id, "harness_id": context.harness_id},
        )
        warm_state = context.extra.get("warm_state", "model")
        recorder.record(
            "telemetry_marker",
            {"phase": "run_start", "warm_state": warm_state, "cold_start": warm_state == "cold"},
        )

        # Build prompt from instruction file text.
        prompt = context.extra.get("prompt")
        if prompt is None:
            ifcand = Path(task.input.instruction_file)
            prompt = (
                ifcand.read_text(encoding="utf-8")
                if ifcand.exists()
                else task.input.instruction_file
            )

        # Sandbox.
        kind = task.execution.sandbox or "local_process"
        try:
            sandbox = build_sandbox(
                kind,
                {
                    "seed_workspace": context.extra.get("seed_workspace"),
                    "image": task.execution.image,
                },
            )
        except Exception as exc:
            recorder.record("exception", {"error": str(exc)})
            recorder.close()
            return self._error_result(run_id, ws, task, context, str(exc), recorder)

        ws_before = None
        try:
            sandbox.prepare()
            ws_before = fingerprint_dir(sandbox.workspace_path())
            start = time.monotonic()
            agent_run = run_agent(
                context.model,
                prompt=prompt,
                system_prompt=context.extra.get("system_prompt"),
                sandbox=sandbox,
                trace=recorder,
                timeout_s=float(task.execution.timeout_seconds),
                max_turns=task.execution.max_turns or 30,
                max_tool_calls=task.execution.max_tool_calls or 120,
                allowed_tools=task.execution.allowed_tools or None,
            )
            duration = time.monotonic() - start
            ws_after = fingerprint_dir(sandbox.workspace_path())

            recorder.record(
                "run_completion",
                {"status": agent_run.status, "turns": len(agent_run.turns), "duration_s": duration},
            )

            # Score the final answer against the oracle.
            aggregate = None
            scores = []
            if agent_run.status == "completed" and not agent_run.error:
                aggregate = score_oracle(task, output=agent_run.final_answer, run_dir=ws.root)
                scores = aggregate.scores
                ws.append_scores([s.model_dump() for s in scores])

            manifest = self._manifest(
                task, context, run_id, ws, aggregate, duration, agent_run, ws_before, ws_after
            )
            ws.write_manifest(manifest)
            ws.write_result(
                {
                    "run_id": run_id,
                    "final_answer": agent_run.final_answer,
                    "error": agent_run.error,
                    "status": agent_run.status,
                    "turns": len(agent_run.turns),
                    "workspace_before": ws_before,
                    "workspace_after": ws_after,
                    "aggregate": aggregate.total if aggregate else None,
                    "passed": bool(aggregate.passed) if aggregate else False,
                    "scores": [s.model_dump() for s in scores] if scores else [],
                    "duration_s": duration,
                }
            )
            write_run_report(ws.root)
            recorder.close()
        finally:
            sandbox.destroy()
            recorder.close()

        status = (
            "completed" if (aggregate is not None and not agent_run.error) else agent_run.status
        )
        if context.store:
            context.store.insert_run(manifest)
            if scores:
                context.store.insert_scores(run_id, [s.model_dump() for s in scores])
            context.store.update_status(
                run_id,
                "completed" if status == "completed" else status,
                aggregate=aggregate.total if aggregate else None,
                passed=bool(aggregate.passed) if aggregate else False,
            )

        return RunResult(
            run_id=run_id,
            run_dir=str(ws.root),
            output=agent_run.final_answer,
            aggregate=aggregate,
            scores=scores,
            manifest=manifest,
            status=status,
            duration_s=duration,
            error=agent_run.error,
        )

    def _error_result(
        self,
        run_id: str,
        ws: RunWorkspace,
        task: TaskSpec,
        context: RunContext,
        error: str,
        recorder: TraceRecorder,
    ) -> RunResult:
        manifest = RunManifest(
            run_id=run_id,
            created_at=datetime.now(UTC),
            task_id=task.id,
            task_version=task.version,
            model_id=context.model_id,
            harness_id=context.harness_id,
            result_status="error",
        ).model_dump(mode="json") | {
            "run_dir": str(ws.root),
            "level": task.level.value,
            "aggregate_score": None,
            "passed": False,
        }
        ws.write_manifest(manifest)
        write_run_report(ws.root)
        return RunResult(
            run_id=run_id,
            run_dir=str(ws.root),
            output="",
            aggregate=None,
            scores=[],
            manifest=manifest,
            status="error",
            duration_s=0.0,
            error=error,
        )

    def _manifest(
        self,
        task: TaskSpec,
        context: RunContext,
        run_id: str,
        ws: RunWorkspace,
        aggregate: AggregateScore | None,
        duration: float,
        agent_run: AgentRun,
        ws_before: str | None,
        ws_after: str | None,
    ) -> dict[str, Any]:
        return RunManifest(
            run_id=run_id,
            created_at=datetime.now(UTC),
            task_id=task.id,
            task_version=task.version,
            model_id=context.model_id,
            harness_id=context.harness_id,
            random_seed=context.seed,
            budgets={
                "timeout_seconds": task.execution.timeout_seconds,
                "max_turns": task.execution.max_turns,
                "max_tool_calls": task.execution.max_tool_calls,
            },
            warm_state="model",
            result_status="completed"
            if (aggregate is not None and not agent_run.error)
            else agent_run.status,
        ).model_dump(mode="json") | {
            "run_dir": str(ws.root),
            "level": task.level.value,
            "aggregate_score": aggregate.total if aggregate else None,
            "passed": bool(aggregate.passed) if aggregate else False,
            "duration_s": duration,
            "turns": len(agent_run.turns),
            "workspace_before": ws_before,
            "workspace_after": ws_after,
        }
