"""Comparison service: expose the Phase 5 analysis engine as a typed service.

Wraps ``analysis.compare_groups``, weighted slicing and Pareto behind a service
so the GUI (and any runner flow) never touches the analysis package inline
(spec 13, correction #3).
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from eval_lab.analysis import (
    Point,
    compare_groups,
    load_run_rows,
    pareto_frontier,
    slice_tasks,
)
from eval_lab.analysis.comparison import ComparisonResult
from eval_lab.analysis.rows import RunRow
from eval_lab.analysis.weighted import SliceAggregate, build_task_rows
from eval_lab.reports.analysis import render_comparison_report
from eval_lab.schemas.models import TaskLabels
from eval_lab.storage.sqlite import RunStore
from eval_lab.tasks.loader import load_task_yaml


class ComparisonService:
    def __init__(
        self,
        *,
        runs_root: str | Path = "runs",
        db: str | Path = "runs/runstore.db",
        tasks_dir: str | Path = "tasks",
    ) -> None:
        self.runs_root = str(runs_root)
        self.db = str(db)
        self.tasks_dir = Path(tasks_dir)

    def _resolver(self, task_id: str) -> TaskLabels | None:
        for p in self.tasks_dir.rglob("*.yaml"):
            try:
                t = load_task_yaml(p)
                if t.id == task_id:
                    return t.labels
            except Exception:
                continue
        return None

    def _rows(self, model_id: str | None = None) -> list[RunRow]:
        store = RunStore(self.db)
        try:
            return load_run_rows(
                store, model_id=model_id, label_resolver=self._resolver, runs_root=self.runs_root
            )
        finally:
            store.close()

    def compare(
        self,
        base_model: str,
        candidate_model: str,
        *,
        regress_threshold: float = 0.05,
    ) -> ComparisonResult:
        return compare_groups(
            self._rows(base_model),
            self._rows(candidate_model),
            base_label=base_model,
            candidate_label=candidate_model,
            regress_threshold=regress_threshold,
        )

    def compare_variants(
        self,
        models: Sequence[str],
        *,
        regress_threshold: float = 0.05,
    ) -> dict[str, dict[str, ComparisonResult]]:
        """Paired A/B across keep-map variants of one source (e.g. free
        full / top-8 / top-4 heads or experts).

        Each variant is a distinct model asset (derivative of the same source);
        running the same suite under each and comparing pairwise yields the
        per-variant deltas that arbitrate prune topology. Keys are
        ``(base_model -> candidate_model)`` with left-to-right order as given.
        """
        out: dict[str, dict[str, ComparisonResult]] = {}
        for i, base in enumerate(models):
            out[base] = {}
            for cand in models[i + 1 :]:
                out[base][cand] = self.compare(base, cand, regress_threshold=regress_threshold)
        return out

    def compare_markdown(self, base_model: str, candidate_model: str) -> str:
        return render_comparison_report(self.compare(base_model, candidate_model))

    def label_slices(self, model_id: str, *, axis: str = "domain") -> dict[str, SliceAggregate]:
        rows = build_task_rows(self._rows(model_id))
        return slice_tasks(rows, axis)

    def pareto(self) -> list[Point]:
        rows = self._rows()
        by_model: dict[str, list[float]] = {}
        latency: dict[str, list[float]] = {}
        for r in rows:
            if r.score is not None and r.duration_s is not None:
                by_model.setdefault(r.model_id, []).append(r.score)
                latency.setdefault(r.model_id, []).append(r.duration_s)
        points = [
            Point(
                label=m,
                quality=sum(v) / len(v),
                latency=sum(latency[m]) / len(latency[m]),
            )
            for m, v in by_model.items()
            if latency.get(m)
        ]
        return pareto_frontier(points)
