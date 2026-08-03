"""Integration tests for Phase 5: weighted suites, compare, pareto CLI."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from eval_lab.adapters.mock import MockModelAdapter
from eval_lab.cli.main import app
from eval_lab.runners.direct import DirectRunner, RunContext
from eval_lab.storage.sqlite import RunStore
from eval_lab.tasks.loader import load_task_yaml

runner = CliRunner()
TASKS = Path(__file__).resolve().parents[2] / "tasks"

TASK_IDS = [
    "reasoning.reverse_string.001",
    "mathematics.basic.addition.001",
    "coding.json_output.001",
]


def _seed(tmp_path: Path) -> RunStore:
    store = RunStore(tmp_path / "runstore.db")
    adapter = MockModelAdapter()
    dr = DirectRunner()
    for model in ("mock-a", "mock-b"):
        for rel in (
            "reasoning/reverse_string/task.yaml",
            "mathematics/basic_addition/task.yaml",
            "coding/json_output/task.yaml",
        ):
            task = load_task_yaml(TASKS / rel)
            dr.execute_task(
                task,
                RunContext(
                    task=task,
                    model=adapter,
                    model_id=model,
                    runs_root=str(tmp_path),
                    store=store,
                ),
            )
    return store


def _write_suite(tmp_path: Path) -> Path:
    p = tmp_path / "suite.yaml"
    p.write_text(
        "schema_version: '1.0'\n"
        "id: suite.phase5.test.001\n"
        "name: Phase5 test suite\n"
        "version: 1\n"
        "family: smoke\n"
        "tasks:\n" + "".join(f"- task_id: {t}\n  weight: 1.0\n" for t in TASK_IDS),
        encoding="utf-8",
    )
    return p


def test_evaluate_weighted_suite(tmp_path: Path) -> None:
    _seed(tmp_path)
    suite = _write_suite(tmp_path)
    result = runner.invoke(
        app,
        [
            "evaluate",
            str(suite),
            "--model",
            "mock-a",
            "--runs-root",
            str(tmp_path),
            "--db",
            str(tmp_path / "runstore.db"),
            "--tasks-dir",
            str(TASKS),
            "--out-dir",
            str(tmp_path / "reports"),
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["model_id"] == "mock-a"
    assert payload["task_count"] == 3
    assert payload["scored_tasks"] == 3
    assert payload["weighted_score"] is not None
    assert payload["report"].endswith(".md")
    assert Path(payload["report"]).is_file()


def test_compare_mock_identical_no_false_regression(tmp_path: Path) -> None:
    _seed(tmp_path)
    result = runner.invoke(
        app,
        [
            "compare",
            "mock-a",
            "mock-b",
            "--runs-root",
            str(tmp_path),
            "--db",
            str(tmp_path / "runstore.db"),
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["sample_size"] == 3
    assert payload["regressions"] == []
    assert payload["improvements"] == []
    assert payload["wins"] == 0 and payload["losses"] == 0 and payload["ties"] == 3
    assert abs(payload["mean_delta"]) <= 1e-9
    assert Path(payload["report"]).is_file()


def test_pareto_frontier_cli(tmp_path: Path) -> None:
    _seed(tmp_path)
    result = runner.invoke(
        app,
        [
            "pareto",
            "--runs-root",
            str(tmp_path),
            "--db",
            str(tmp_path / "runstore.db"),
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    labels = {p["label"] for p in payload["all"]}
    assert {"mock-a", "mock-b"} <= labels
    assert payload["frontier"]


def test_compare_variants_builds_pairwise_keepmap_matrix(tmp_path: Path) -> None:
    """compare_variants returns a (base -> candidate) A/B matrix across keep-map
    variants of one source, so full/top-8/top-4 arbitration is explicit."""
    from eval_lab.services.comparisons import ComparisonService

    store = RunStore(tmp_path / "runstore.db")
    adapter = MockModelAdapter()
    dr = DirectRunner()
    variants = ("full", "top8", "top4")
    rels = (
        "reasoning/reverse_string/task.yaml",
        "mathematics/basic_addition/task.yaml",
        "coding/json_output/task.yaml",
    )
    for model in variants:
        for rel in rels:
            task = load_task_yaml(TASKS / rel)
            dr.execute_task(
                task,
                RunContext(
                    task=task,
                    model=adapter,
                    model_id=model,
                    runs_root=str(tmp_path),
                    store=store,
                ),
            )
    store.close()

    svc = ComparisonService(runs_root=str(tmp_path), db=str(tmp_path / "runstore.db"))
    matrix = svc.compare_variants(list(variants))
    assert set(matrix) == set(variants)
    assert set(matrix["full"]) == {"top8", "top4"}
    assert set(matrix["top8"]) == {"top4"}
    assert matrix["full"]["top4"].sample_size == 3
    # Identical mock runs must never report a false regression between variants.
    assert matrix["full"]["top4"].regressions == ()
    assert matrix["top8"]["top4"].wins == 0
