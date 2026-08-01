"""Integration tests for the read-only dashboard API (serve extra)."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402 - after importorskip

from eval_lab.adapters.mock import MockModelAdapter  # noqa: E402
from eval_lab.dashboard import create_app  # noqa: E402
from eval_lab.runners.direct import DirectRunner, RunContext  # noqa: E402
from eval_lab.storage.sqlite import RunStore  # noqa: E402
from eval_lab.tasks.loader import load_task_yaml  # noqa: E402

TASKS = Path(__file__).resolve().parents[2] / "tasks"


def _seed_runs(tmp_path: Path) -> RunStore:
    store = RunStore(tmp_path / "runstore.db")
    adapter = MockModelAdapter()
    runner = DirectRunner()
    for task_rel, model in (
        ("reasoning/reverse_string/task.yaml", "mock-a"),
        ("coding/json_output/task.yaml", "mock-a"),
        ("mathematics/basic_addition/task.yaml", "mock-b"),
    ):
        task = load_task_yaml(TASKS / task_rel)
        runner.execute_task(
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


def test_health_and_overview(tmp_path: Path) -> None:
    _seed_runs(tmp_path)
    client = TestClient(create_app(tmp_path, tmp_path / "runstore.db"))
    h = client.get("/api/health")
    assert h.status_code == 200 and h.json()["status"] == "ok"

    ov = client.get("/api/overview").json()
    assert ov["total_runs"] == 3
    assert ov["scored_runs"] == 3
    assert set(ov["models"]) == {"mock-a", "mock-b"}
    assert ov["avg_aggregate_score"] is not None


def test_models_endpoint_run_times(tmp_path: Path) -> None:
    _seed_runs(tmp_path)
    client = TestClient(create_app(tmp_path, tmp_path / "runstore.db"))
    models = client.get("/api/models").json()
    by_id = {m["model_id"]: m for m in models}
    assert set(by_id) == {"mock-a", "mock-b"}
    assert by_id["mock-a"]["run_count"] == 2
    assert by_id["mock-b"]["run_count"] == 1
    # Every seeded run has a real duration_s in its manifest.
    for m in models:
        assert m["median_duration_s"] is not None
        assert m["median_duration_s"] >= 0
        assert 0 <= m["min_duration_s"] <= m["max_duration_s"]
    # Sorted by model id, latest_duration == max for a single-run model.
    assert by_id["mock-b"]["latest_duration_s"] == by_id["mock-b"]["max_duration_s"]


def test_runs_list_and_filters(tmp_path: Path) -> None:
    _seed_runs(tmp_path)
    client = TestClient(create_app(tmp_path, tmp_path / "runstore.db"))
    runs = client.get("/api/runs").json()
    assert len(runs) == 3

    only_a = client.get("/api/runs", params={"model_id": "mock-a"}).json()
    assert len(only_a) == 2

    missing = client.get("/api/runs", params={"model_id": "nope"}).json()
    assert missing == []


def test_run_detail_includes_manifest_scores(tmp_path: Path) -> None:
    _seed_runs(tmp_path)
    client = TestClient(create_app(tmp_path, tmp_path / "runstore.db"))
    runs = client.get("/api/runs").json()
    run_id = runs[0]["run_id"]
    detail = client.get(f"/api/runs/{run_id}").json()
    assert detail["run"]["run_id"] == run_id
    assert detail["manifest"]["model_id"] is not None
    assert isinstance(detail["scores"], list)
    assert any(s.get("scorer_id") for s in detail["scores"]), "scores must carry scorer ids"

    assert client.get("/api/runs/does-not-exist").status_code == 404


def test_trace_and_telemetry_serialize(tmp_path: Path) -> None:
    _seed_runs(tmp_path)
    client = TestClient(create_app(tmp_path, tmp_path / "runstore.db"))
    run_id = client.get("/api/runs").json()[0]["run_id"]
    trace = client.get(f"/api/runs/{run_id}/trace").json()
    # Direct runner always records these event types.
    types = {e["event_type"] for e in trace}
    assert {"run_start", "model_completion"}.issubset(types)

    telem = client.get(f"/api/runs/{run_id}/telemetry").json()
    assert telem["run_id"] == run_id
    assert isinstance(telem["series"], dict)
