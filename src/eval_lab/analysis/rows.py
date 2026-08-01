"""Run-row data model and loaders for analysis (Phase 5).

Analysis works over lightweight, immutable :class:`RunRow` records rather than
the persistence layer directly, so every comparison/slice function is pure and
unit-testable. Rows are loaded from the SQLite index plus the portable run
manifest (for duration), with task labels resolved from the task catalogue.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from eval_lab.schemas.models import TaskLabels
from eval_lab.storage.sqlite import RunStore

# Resolves a task id to its labels (None when the catalog cannot resolve it).
LabelResolver = Callable[[str], TaskLabels | None]


def task_labels_to_map(labels: TaskLabels) -> dict[str, frozenset[str]]:
    """Export the label dimensions that slicing can group by."""
    return {
        "domain": frozenset(labels.domains),
        "capability": frozenset(labels.capabilities),
        "modality": frozenset(labels.modalities),
        "trajectory_stage": frozenset(labels.trajectory_stages),
        "failure_mode": frozenset(labels.failure_modes_targeted),
        "intervention": frozenset(labels.intervention),
        "difficulty": frozenset([labels.difficulty]),
    }


@dataclass(frozen=True)
class RunRow:
    """One executed task repetition ready for aggregation."""

    run_id: str
    task_id: str
    task_version: int
    model_id: str
    suite_id: str | None
    task_level: str | None
    seed: int | None
    score: float | None
    passed: bool | None
    duration_s: float | None
    labels: Mapping[str, frozenset[str]] = field(default_factory=dict)
    # Extra numeric resources (e.g. peak memory) for resource-delta comparison.
    resources: Mapping[str, float] = field(default_factory=dict)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _manifest_duration(run_dir: str | Path) -> float | None:
    """Read ``duration_s`` from a run manifest, tolerating a missing file."""
    data = _read_json(Path(run_dir) / "manifest.json")
    value = data.get("duration_s")
    return float(value) if isinstance(value, (int, float)) else None


def load_run_rows(
    store: RunStore,
    *,
    model_id: str | None = None,
    suite_id: str | None = None,
    label_resolver: LabelResolver | None = None,
    runs_root: str | Path | None = None,
) -> list[RunRow]:
    """Load completed runs from the index as :class:`RunRow` records.

    ``runs_root`` locates manifests for duration (defaults to the store's db
    parent). Only indexed runs are returned; the caller filters by model/suite.
    """
    rows: list[RunRow] = []
    base = Path(runs_root) if runs_root is not None else store.db_path.parent
    for r in store.list_runs(limit=100_000):
        mid = r.get("model_id")
        sid = r.get("suite_id")
        if model_id is not None and mid != model_id:
            continue
        if suite_id is not None and sid != suite_id:
            continue
        task_id = str(r["task_id"])
        task_spec = label_resolver(task_id) if label_resolver else None
        labels = task_labels_to_map(task_spec) if task_spec else {}
        run_dir = r.get("run_dir")
        run_dir_path = Path(str(run_dir)) if run_dir else base / str(r["run_id"])
        score_raw = r.get("aggregate_score")
        passed_raw = r.get("passed")
        task_version_raw = r.get("task_version")
        rows.append(
            RunRow(
                run_id=str(r["run_id"]),
                task_id=task_id,
                task_version=(
                    int(task_version_raw) if isinstance(task_version_raw, (int, float)) else 0
                ),
                model_id=str(mid) if mid else "",
                suite_id=str(sid) if sid else None,
                task_level=str(r["level"]) if r.get("level") else None,
                seed=None,
                score=float(score_raw) if isinstance(score_raw, (int, float)) else None,
                passed=bool(passed_raw) if passed_raw is not None else None,
                duration_s=_manifest_duration(run_dir_path),
                labels=labels,
            )
        )
    return rows
