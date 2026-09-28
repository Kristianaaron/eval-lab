"""Catalogue integrity: every task loads, its fixtures exist, every benchmark
suite resolves, and every shipped reference solution scores 1.0 on its task's
hidden tests while the unmodified fixture (or a naive answer) does not.

Reference solutions live under ``tests/fixtures/reference_solutions``:
- ``<task_id>.py`` — module text a direct task's model reply would contain
  (wrapped in a fenced block here) for ``python_tests`` extract-mode tasks.
- ``<task_id>/`` — overlay files applied onto an agentic task's workspace
  fixture before both oracles run in workspace mode.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from eval_lab.scorers.aggregate import _instantiate, score_oracle
from eval_lab.scorers.base import get_scorer
from eval_lab.tasks.loader import check_fixture_references, load_suite_yaml, load_task_yaml
from eval_lab.tasks.resolve import build_prompt, fixture_dir

REPO = Path(__file__).resolve().parents[2]
TASKS = REPO / "tasks"
SUITES = REPO / "configs" / "suites"
REFS = REPO / "tests" / "fixtures" / "reference_solutions"

ALL_TASK_FILES = sorted(TASKS.rglob("task.yaml"))


def _load_all() -> dict[str, object]:
    index = {}
    for p in ALL_TASK_FILES:
        t = load_task_yaml(p)
        index[t.id] = t
    return index


def test_every_task_loads_with_unique_ids_and_present_fixtures() -> None:
    seen: dict[str, Path] = {}
    for p in ALL_TASK_FILES:
        t = load_task_yaml(p)
        assert t.id not in seen, f"duplicate task id {t.id}: {p} and {seen[t.id]}"
        seen[t.id] = p
        assert not check_fixture_references(t, p.parent), f"missing fixtures for {t.id}"
        assert t.source_dir == str(p.parent.resolve())
        prompt = build_prompt(t)
        assert prompt.strip() and prompt != t.input.instruction_file, f"{t.id}: prompt unresolved"
        if t.execution.runner == "perplexity":
            assert t.input.attachments, f"{t.id}: perplexity task needs a corpus attachment"
        for ref in t.oracle:
            _instantiate(get_scorer(ref.type), ref.config)  # config must be accepted
            if ref.type == "python_tests":
                tests_dir = p.parent / ref.config.get("tests", "tests")
                assert tests_dir.is_dir(), f"{t.id}: hidden tests dir missing"
                assert list(tests_dir.glob("test*.py")), f"{t.id}: no test files"
    assert len(seen) >= 60


@pytest.mark.parametrize(
    "suite_path", sorted(SUITES.glob("benchmark-*.yaml")), ids=lambda p: p.stem
)
def test_benchmark_suites_resolve_to_existing_tasks(suite_path: Path) -> None:
    index = _load_all()
    suite = load_suite_yaml(suite_path)
    assert suite.family == "benchmark"
    missing = [r.task_id for r in suite.tasks if r.task_id not in index]
    assert not missing, f"{suite_path.name} references unknown tasks: {missing}"
    assert len(suite.tasks) >= 3


def _direct_refs() -> list[Path]:
    return sorted(REFS.glob("*.py")) if REFS.is_dir() else []


def _overlay_refs() -> list[Path]:
    return sorted(p for p in REFS.iterdir() if p.is_dir()) if REFS.is_dir() else []


@pytest.mark.parametrize("ref", _direct_refs(), ids=lambda p: p.stem)
def test_direct_reference_solution_passes_hidden_tests(ref: Path) -> None:
    index = _load_all()
    task = index.get(ref.stem)
    assert task is not None, f"reference {ref.name} has no task"
    good = score_oracle(task, output="```python\n" + ref.read_text(encoding="utf-8") + "\n```")
    details = [s.details for s in good.scores]
    assert good.passed and good.total == 1.0, f"{task.id}: reference failed {details}"
    tests_run = sum(int(s.details.get("tests_total", 0)) for s in good.scores)
    assert tests_run >= 10, f"{task.id}: only {tests_run} hidden tests"
    naive = score_oracle(task, output="```python\npass\n```")
    assert not naive.passed and naive.total < 1.0


@pytest.mark.parametrize("ref", _overlay_refs(), ids=lambda p: p.name)
def test_agentic_reference_overlay_passes_both_oracles(ref: Path, tmp_path: Path) -> None:
    index = _load_all()
    task = index.get(ref.name)
    assert task is not None, f"overlay {ref.name} has no task"
    fixture = fixture_dir(task)
    assert fixture is not None
    ws = tmp_path / "ws"
    shutil.copytree(fixture, ws)
    before = score_oracle(task, output="", run_dir=ws)
    assert not before.passed, f"{task.id}: unmodified workspace already passes"
    shutil.copytree(ref, ws, dirs_exist_ok=True)
    after = score_oracle(task, output="", run_dir=ws)
    assert after.passed and after.total == 1.0, f"{task.id}: {[s.details for s in after.scores]}"
    hidden = [s for s in after.scores if s.scorer_id == "python_tests"]
    assert hidden and int(hidden[0].details["tests_total"]) >= 10
