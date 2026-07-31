"""Load and validate task specs from YAML (spec 6.1, 8)."""

from __future__ import annotations

from pathlib import Path

import yaml

from eval_lab.schemas.models import SuiteSpec, TaskSpec


class TaskLoadError(ValueError):
    """Raised when a task or suite file cannot be parsed or validated."""


def load_task_yaml(path: str | Path) -> TaskSpec:
    """Load and validate a single task YAML file."""
    p = Path(path)
    if not p.exists():
        raise TaskLoadError(f"task file not found: {p}")
    try:
        raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:  # pragma: no cover - defensive
        raise TaskLoadError(f"invalid YAML in {p}: {exc}") from exc
    if not isinstance(raw, dict):
        raise TaskLoadError(f"task file must contain a mapping, got {type(raw).__name__}: {p}")
    try:
        return TaskSpec.model_validate(raw)
    except Exception as exc:  # pydantic ValidationError
        raise TaskLoadError(f"task validation failed for {p}: {exc}") from exc


def load_suite_yaml(path: str | Path) -> SuiteSpec:
    """Load and validate a single suite YAML file."""
    p = Path(path)
    if not p.exists():
        raise TaskLoadError(f"suite file not found: {p}")
    try:
        raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:  # pragma: no cover - defensive
        raise TaskLoadError(f"invalid YAML in {p}: {exc}") from exc
    if not isinstance(raw, dict):
        raise TaskLoadError(f"suite file must contain a mapping, got {type(raw).__name__}: {p}")
    try:
        return SuiteSpec.model_validate(raw)
    except Exception as exc:
        raise TaskLoadError(f"suite validation failed for {p}: {exc}") from exc


def check_fixture_references(task: TaskSpec, base_dir: str | Path) -> list[str]:
    """Check that workspace fixtures referenced by a task exist relative to base_dir.

    Returns a list of missing fixture paths (empty when all resolve).
    """
    base = Path(base_dir)
    missing: list[str] = []
    fixture = task.input.workspace_fixture
    if fixture:
        candidate = base / fixture
        if not candidate.exists():
            missing.append(str(candidate))
    for attachment in task.input.attachments:
        candidate = base / attachment
        if not candidate.exists():
            missing.append(str(candidate))
    return missing
