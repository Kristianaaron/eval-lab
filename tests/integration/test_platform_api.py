"""Integration tests: Milestone 2 + corrections API (jobs, eval launch, env, comparisons)."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from eval_lab.dashboard import create_app  # noqa: E402

TERMINAL = {"completed", "completed_with_warnings", "failed", "failed_recoverable", "cancelled"}


def _client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(tmp_path / "runs", models_root=tmp_path / "models"))


def test_environment_endpoint(tmp_path: Path) -> None:
    c = _client(tmp_path)
    env = c.get("/api/environment").json()
    assert env["software_version"]
    assert env["nodes"] >= 1
    assert env["unified_memory_gb"] > 0


def test_eval_config_lists_models_and_suites(tmp_path: Path) -> None:
    c = _client(tmp_path)
    cfg = c.get("/api/eval-config").json()
    assert any(m["model_id"] == "mock" for m in cfg["models"])
    assert any(s["family"] == "smoke" or "smoke" in s["id"] for s in cfg["suites"])
    assert cfg["harnesses"]


def test_eval_job_create_run_complete(tmp_path: Path) -> None:
    c = _client(tmp_path)
    r = c.post(
        "/api/eval-jobs",
        json={
            "model_asset_id": "mock-deterministic",
            "model_id": "mock",
            "harness_id": "direct",
            "suite_ref": "configs/suites/smoke_direct.yaml",
            "repeat_count": 1,
            "runs_root": str(tmp_path / "runs"),
        },
    )
    assert r.status_code == 200
    job = r.json()
    job_id = job["job_id"]

    for _ in range(200):
        j = c.get(f"/api/eval-jobs/{job_id}").json()
        if j["state"] in TERMINAL:
            break
        time.sleep(0.05)
    assert j["state"] in ("completed", "completed_with_warnings")
    assert j["progress"]["done"] == j["progress"]["total"] == 5
    assert len(j["result"]["run_ids"]) == 5
    # Runs are recorded in the shared run index -> auditable.
    runs = c.get("/api/runs").json()
    assert any(r["run_id"] in j["result"]["run_ids"] for r in runs)

    # Job appears in the generic jobs listing.
    jobs = c.get("/api/jobs").json()
    assert any(jj["job_id"] == job_id for jj in jobs)


def test_eval_job_cancel_marks_request(tmp_path: Path) -> None:
    c = _client(tmp_path)
    job = c.post(
        "/api/eval-jobs",
        json={
            "model_asset_id": "mock-deterministic",
            "model_id": "mock",
            "suite_ref": "configs/suites/smoke_direct.yaml",
            "runs_root": str(tmp_path / "runs"),
        },
    ).json()
    job_id = job["job_id"]
    # Cancel immediately (may complete first; assert it ends cancelled OR completed).
    c.post(f"/api/eval-jobs/{job_id}/cancel", json={})
    for _ in range(200):
        j = c.get(f"/api/eval-jobs/{job_id}").json()
        if j["state"] in TERMINAL:
            break
        time.sleep(0.05)
    assert j["state"] in ("cancelled", "completed", "completed_with_warnings")


def test_comparisons_pareto_and_slices(tmp_path: Path) -> None:
    c = _client(tmp_path)
    # Seed a couple of comparable runs by launching a mock eval.
    r = c.post(
        "/api/eval-jobs",
        json={
            "model_asset_id": "mock-deterministic",
            "model_id": "mock",
            "suite_ref": "configs/suites/smoke_direct.yaml",
            "runs_root": str(tmp_path / "runs"),
        },
    )
    job_id = r.json()["job_id"]
    for _ in range(200):
        j = c.get(f"/api/eval-jobs/{job_id}").json()
        if j["state"] in TERMINAL:
            break
        time.sleep(0.05)
    assert c.get("/api/comparisons/pareto").status_code == 200
    slices = c.get("/api/comparisons/slices", params={"model": "mock", "axis": "domain"}).json()
    assert slices["model"] == "mock"
    assert isinstance(slices["slices"], dict)
