"""Evaluation service: runnable-model evaluation jobs on the orchestrator (correction #3, M2).

Wraps the existing runners + orchestrator behind a typed service. The GUI never
touches runner, storage, or telemetry internals; it calls ``launch``/``get``/
``list``/``cancel`` and receives a persisted :class:`Job` with real progress.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from eval_lab.adapters.base import ModelAdapter
from eval_lab.adapters.mock import MockModelAdapter
from eval_lab.runners.direct import DirectRunner, RunContext
from eval_lab.schemas.evaluation import EvaluationConfig
from eval_lab.schemas.job import Job, JobResult, JobState
from eval_lab.schemas.models import SuiteSpec, TaskSpec
from eval_lab.services.leakage import check_leakage
from eval_lab.services.orchestrator import JobCancelled, JobContext, JobOrchestrator
from eval_lab.storage.sqlite import RunStore
from eval_lab.tasks.loader import load_suite_yaml, load_task_yaml

ModelFactory = Callable[[Job], ModelAdapter]


TasksIndex = dict[str, TaskSpec]


def _resolve_suite(suite_ref: str, suites_dir: Path) -> SuiteSpec:
    path = Path(suite_ref)
    if not path.is_file():
        for cand in (suites_dir / f"{suite_ref}.yaml", suites_dir / f"{suite_ref}.yml"):
            if cand.is_file():
                path = cand
                break
    if not path.is_file():
        raise ValueError(f"suite not found: {suite_ref}")
    return load_suite_yaml(path)


def _index_tasks(tasks_dir: Path) -> TasksIndex:
    index: TasksIndex = {}
    for p in tasks_dir.rglob("*.yaml"):
        try:
            t = load_task_yaml(p)
            index[t.id] = t
        except Exception:
            continue
    return index


def _expand_tasks(
    suite: SuiteSpec, cfg: EvaluationConfig, tasks_by_id: TasksIndex
) -> list[tuple[TaskSpec, None]]:
    expanded: list[tuple[TaskSpec, None]] = []
    for ref in suite.tasks:
        task = tasks_by_id.get(ref.task_id)
        if task is None:
            continue
        if cfg.label_filters and not any(
            f in set(task.labels.domains) | set(task.labels.capabilities) for f in cfg.label_filters
        ):
            continue
        reps = ref.repetitions or cfg.repeat_count
        for _ in range(reps):
            expanded.append((task, None))
    return expanded


def make_evaluation_executor(
    *,
    runs_root: str | Path = "runs",
    db: str | None = None,
    tasks_dir: str | Path = "tasks",
    suites_dir: str | Path = "configs/suites",
    model_factory: ModelFactory | None = None,
) -> Callable[[Job, JobContext], None]:
    """Build the orchestrator executor for kind == 'evaluation'."""
    tasks_dir = Path(tasks_dir)
    suites_dir = Path(suites_dir)
    factory = model_factory or (lambda _job: MockModelAdapter())

    def executor(job: Job, ctx: JobContext) -> None:
        cfg = EvaluationConfig.model_validate(job.config)
        ctx.set_stage("validating")
        suite = _resolve_suite(cfg.suite_ref, suites_dir)
        tasks_by_id = _index_tasks(tasks_dir)
        expanded = _expand_tasks(suite, cfg, tasks_by_id)
        if not expanded:
            raise ValueError("suite resolved to zero tasks")

        # Leakage guard: calibration partition must not be treated as held-out.
        resolved = list({t.id: t for t, _ in expanded}.values())
        leakage = check_leakage(resolved, calibration_ids=None)
        if leakage.detected:
            ctx.set_progress(0, len(expanded), detail=leakage.message)

        ctx.set_stage("launching_model")
        model = factory(job)
        ctx.set_stage("running_tasks")

        store = RunStore(db) if db else RunStore(Path(runs_root) / "runstore.db")
        runner = DirectRunner()
        run_ids: list[str] = []
        try:
            for idx, (task, seed) in enumerate(expanded, start=1):
                if ctx.should_stop():
                    raise JobCancelled()
                ctx.set_progress(idx - 1, len(expanded), detail=task.id)
                rec = runner.execute_task(
                    task,
                    RunContext(
                        task=task,
                        model=model,
                        model_id=cfg.model_id,
                        seed=seed,
                        runs_root=cfg.runs_root or str(runs_root),
                        store=store,
                    ),
                )
                run_ids.append(rec.run_id)
                ctx.set_progress(idx, len(expanded), detail=task.id)
        finally:
            store.close()

        ctx.set_stage("scoring")
        ctx.set_stage("generating_report")
        ctx.set_result(
            JobResult(
                run_ids=run_ids,
                extra={
                    "leakage_overlap": leakage.overlapping_task_ids,
                    "leakage_blocked": leakage.blocked,
                },
            )
        )
        ctx.finish(JobState.completed_with_warnings if leakage.detected else JobState.completed)

    return executor


class EvaluationService:
    def __init__(
        self,
        jobs_root: str | Path,
        *,
        runs_root: str | Path = "runs",
        db: str | Path | None = None,
        tasks_dir: str | Path = "tasks",
        suites_dir: str | Path = "configs/suites",
        model_factory: ModelFactory | None = None,
        orchestrator: JobOrchestrator | None = None,
    ) -> None:
        self.orchestrator = orchestrator or JobOrchestrator(jobs_root)
        self.runs_root = str(runs_root)
        self.db = str(db) if db is not None else None
        executor = make_evaluation_executor(
            runs_root=runs_root,
            db=self.db,
            tasks_dir=tasks_dir,
            suites_dir=suites_dir,
            model_factory=model_factory,
        )
        self.orchestrator.register("evaluation", executor)

    def launch(self, cfg: EvaluationConfig, *, name: str | None = None) -> Job:
        return self.orchestrator.submit("evaluation", cfg.model_dump(mode="json"), name=name)

    def get(self, job_id: str) -> Job | None:
        return self.orchestrator.get(job_id)

    def list(self) -> list[Job]:
        return self.orchestrator.list(kind="evaluation")

    def cancel(self, job_id: str) -> Job | None:
        return self.orchestrator.cancel(job_id)
