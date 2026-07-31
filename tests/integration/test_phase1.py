"""Phase 1 end-to-end tests: direct runner, scorers, persistence, reports."""

from __future__ import annotations

from pathlib import Path

from eval_lab.adapters.mock import MockModelAdapter
from eval_lab.reports.markdown import render_run_report
from eval_lab.runners.direct import DirectRunner, RunContext
from eval_lab.scorers.aggregate import score_oracle
from eval_lab.storage.artifacts import RunWorkspace, fingerprint_dir
from eval_lab.storage.sqlite import RunStore

TASKS = Path(__file__).parent.parent.parent / "tasks"


def _load_all_direct():
    from eval_lab.tasks.loader import load_task_yaml

    ids = [
        "mathematics.basic.addition.001",
        "reasoning.reverse_string.001",
        "general.knowledge.capital_facts.001",
        "coding.json_output.001",
        "reasoning.exists_statement.001",
    ]
    result = []
    for p in TASKS.rglob("*.yaml"):
        t = load_task_yaml(p)
        if t.id in ids:
            result.append(t)
    return result


def test_five_direct_tasks_run_end_to_end(tmp_path):
    tasks = _load_all_direct()
    assert len(tasks) == 5, f"expected 5 direct tasks, got {len(tasks)}"
    adapter = MockModelAdapter()
    store = RunStore(tmp_path / "runs.db")
    runner = DirectRunner()
    results = []
    for t in tasks:
        ctx = RunContext(
            task=t, model=adapter, model_id="mock", runs_root=str(tmp_path / "runs"), store=store
        )
        results.append(runner.execute_task(t, ctx))
    store.close()

    assert all(r.aggregate is not None for r in results), (
        "all runs should produce an aggregate score"
    )
    assert all(r.status == "completed" for r in results), "no model errors expected with mock"
    # All 5 persisted in sqlite and got reports.
    for r in results:
        assert (Path(r.run_dir) / "manifest.json").exists()
        assert (Path(r.run_dir) / "result.json").exists()
        assert (Path(r.run_dir) / "trace.jsonl").exists()
        assert (Path(r.run_dir) / "report.md").exists()


def test_repeated_deterministic_runs_identical(tmp_path):
    adapter = MockModelAdapter()
    runner = DirectRunner()
    t = _load_all_direct()[0]
    results = []
    for _ in range(2):
        ctx = RunContext(task=t, model=adapter, model_id="mock", runs_root=str(tmp_path / "runs"))
        results.append(runner.execute_task(t, ctx))
    a, b = results
    assert a.output == b.output
    assert a.aggregate.total == b.aggregate.total
    assert a.aggregate.passed == b.aggregate.passed


def test_scorers_all_work():
    from eval_lab.schemas.models import TaskLabels, TaskSpec

    task = TaskSpec(
        id="re.j.d.001",
        name="t",
        description="d",
        labels=TaskLabels(domains=["mathematics"]),
        input={"instruction_file": "p"},
        execution={"runner": "direct"},
        oracle=[
            {
                "type": "json_schema",
                "config": {
                    "properties": {"id": {"type": "string"}, "ok": {"type": "boolean"}},
                    "required": ["id", "ok"],
                },
                "weight": 0.6,
                "required": True,
            },
            {"type": "regex", "config": {"pattern": "mock"}, "weight": 0.4},
        ],
    )
    agg = score_oracle(task, output='{"id": "mock", "ok": true}')
    assert agg.passed
    assert agg.total > 0.9

    bad = score_oracle(task, output="not json")
    assert not bad.passed
    assert bad.required_failures  # required json_schema failed


def test_run_workspace_hashes_dir(tmp_path):
    (tmp_path / "a.txt").write_text("hello")
    h1 = fingerprint_dir(tmp_path)
    (tmp_path / "a.txt").write_text("changing")
    h2 = fingerprint_dir(tmp_path)
    assert h1 != h2
    ws = RunWorkspace(tmp_path / "runs", "abc123")
    ws.store_artifact("out.txt", "data")
    assert (tmp_path / "runs" / "abc123" / "artifacts" / "out.txt").exists()


def test_markdown_report_render(tmp_path):
    ws = RunWorkspace(tmp_path, "r1")
    manifest = {"run_id": "r1", "task_id": "a.b.c.001", "model_id": "mock"}
    result = {
        "run_id": "r1",
        "aggregate": 0.8,
        "passed": True,
        "duration_s": 1.2,
        "scores": [{"scorer_id": "regex", "score": 1.0, "passed": True, "required": True}],
        "output": "hello",
    }
    ws.write_manifest(manifest)
    ws.write_result(result)
    md = render_run_report(ws.root)
    assert "r1" in md
    assert "regex" in md
    assert "hello" in md
