"""Load and validate task specs from YAML (spec 6.1, 8)."""

from __future__ import annotations

from pathlib import Path

import yaml

from eval_lab.schemas.models import SuiteSpec, TaskSpec


class TaskLoadError(ValueError):
    """Raised when a task or suite file cannot be parsed or validated."""


def _package_path(package: Path, value: str) -> str:
    """Return a safe absolute task-package path without following symlinks."""

    relative = Path(value)
    if (
        not value
        or relative.is_absolute()
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise TaskLoadError("task asset path must be package-relative")
    root = package.resolve(strict=True)
    candidate = root.joinpath(*relative.parts)
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise TaskLoadError("task asset path must not use symlinks")
    # Rejecting '..' makes this true even for an intentionally absent optional
    # fixture, which is reported later by check_fixture_references.
    if not candidate.is_relative_to(root):
        raise TaskLoadError("task asset path escapes its package")
    return str(candidate)


def load_task_yaml(path: str | Path) -> TaskSpec:
    """Load and validate a single task YAML file."""
    p = Path(path)
    if not p.exists():
        raise TaskLoadError(f"task file not found: {p}")
    if p.is_symlink():
        raise TaskLoadError(f"task file must not be a symlink: {p}")
    try:
        raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:  # pragma: no cover - defensive
        raise TaskLoadError(f"invalid YAML in {p}: {exc}") from exc
    if not isinstance(raw, dict):
        raise TaskLoadError(f"task file must contain a mapping, got {type(raw).__name__}: {p}")
    try:
        task = TaskSpec.model_validate(raw)
        package = p.parent
        task.input.instruction_file = _package_path(package, task.input.instruction_file)
        task.input.attachments = [_package_path(package, item) for item in task.input.attachments]
        if task.input.workspace_fixture is not None:
            task.input.workspace_fixture = _package_path(package, task.input.workspace_fixture)
        return task
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
