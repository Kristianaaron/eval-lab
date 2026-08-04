"""Integration tests: experiments (M5) backed by imported atlas runs."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from eval_lab.dashboard import create_app  # noqa: E402


def _write_fixture_run(tmp_path: Path, run_id: str = "atlas-exp-1") -> Path:
    """Write a conformant atlas export dir (run_manifest + saliency + plans + derivative)."""
    run_dir = tmp_path / "atlas_out" / "atlas_runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "run_manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "atlas-bridge-v1",
                "atlas_run_id": run_id,
                "source_arch": "k3-mini",
                "calibration_suite_id": "atlas_calibration",
                "evidence_level": "basic_saliency",
                "status": "completed",
                "n_tasks": 5,
                "evidence_present": [
                    "run_manifest.json",
                    "layer_saliency.json",
                    "plans.json",
                    "derivative.json",
                ],
            }
        )
    )
    (run_dir / "layer_saliency.json").write_text(
        json.dumps(
            [
                {
                    "layer": 0,
                    "expert": 0,
                    "label": "code_generation",
                    "mean": 0.9,
                    "total_value": 0.9,
                },
                {
                    "layer": 0,
                    "expert": 1,
                    "label": "code_generation",
                    "mean": 0.4,
                    "total_value": 0.4,
                },
            ]
        )
    )
    (run_dir / "plans.json").write_text(
        json.dumps(
            [
                {
                    "name": "keep4-value",
                    "strategy": "value",
                    "keep_per_layer": 4,
                    "kept_per_layer": {"0": 2},
                    "resident_bytes_a": 500.0,
                    "resident_bytes_b": 0.0,
                    "keep_map": {
                        "source_model_id": "k3-mini",
                        "entries": [
                            {
                                "layer_index": 0,
                                "source_expert_id": 0,
                                "keep": True,
                                "reason": "saliency",
                            },
                            {
                                "layer_index": 0,
                                "source_expert_id": 1,
                                "keep": True,
                                "reason": "saliency",
                            },
                        ],
                    },
                    "precision": {"entries": []},
                }
            ]
        )
    )
    (run_dir / "derivative.json").write_text(
        json.dumps(
            {
                "model_asset_id": "deriv-test",
                "display_name": "k3-mini keep4-value",
                "asset_type": "derivative_checkpoint",
                "model_family": "k3-mini",
                "architecture": "k3-mini",
                "checkpoint_path": "/models/derivatives/keep4-value",
                "parent_model_id": "src-k3-mini",
                "kept_per_layer": {"0": 2},
                "stored_size_bytes": 500,
                "estimated_resident_bytes": 900,
                "identity_source_slots": {"l0e0": "0"},
            }
        )
    )
    return run_dir


def _client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(tmp_path / "runs", models_root=tmp_path / "models"))


def _import(c, run_id: str) -> dict:
    r = c.post("/api/atlas-bridge/import", json={"run_id": run_id})
    assert r.status_code == 200, r.text
    return r.json()


def test_experiment_create_list_get_delete(tmp_path: Path) -> None:
    _write_fixture_run(tmp_path)
    c = _client(tmp_path)
    _import(c, "atlas-exp-1")

    created = c.post(
        "/api/experiments",
        json={
            "run_id": "atlas-exp-1",
            "plan_name": "keep4-value",
            "objective": "retain code_generation",
            "memory_target_bytes": 600,
        },
    )
    assert created.status_code == 200, created.text
    exp = created.json()
    assert exp["run_id"] == "atlas-exp-1"
    assert exp["plan_name"] == "keep4-value"
    assert exp["total_kept"] == 2
    assert exp["kept_per_layer"] == {"0": 2}
    # derivative built for the run is linked
    assert exp["derivate_asset_id"] == "deriv-test"
    assert exp["source_asset_id"] == "src-k3-mini"

    listed = c.get("/api/experiments").json()
    assert [e["experiment_id"] for e in listed] == [exp["experiment_id"]]

    got = c.get(f"/api/experiments/{exp['experiment_id']}")
    assert got.status_code == 200
    assert got.json()["objective"] == "retain code_generation"

    deleted = c.delete(f"/api/experiments/{exp['experiment_id']}")
    assert deleted.json()["deleted"] is True
    assert c.get(f"/api/experiments/{exp['experiment_id']}").status_code == 404


def test_experiment_bad_plan_and_missing_run(tmp_path: Path) -> None:
    _write_fixture_run(tmp_path)
    c = _client(tmp_path)
    _import(c, "atlas-exp-1")

    r = c.post("/api/experiments", json={"run_id": "atlas-exp-1", "plan_name": "nope"})
    assert r.status_code == 400

    r2 = c.post("/api/experiments", json={"run_id": "missing-run", "plan_name": "keep4-value"})
    assert r2.status_code == 404


def test_experiment_links_derivative_model_asset(tmp_path: Path) -> None:
    _write_fixture_run(tmp_path)
    c = _client(tmp_path)
    _import(c, "atlas-exp-1")

    created = c.post(
        "/api/experiments", json={"run_id": "atlas-exp-1", "plan_name": "keep4-value"}
    ).json()

    # the derivative was registered as a model asset by the bridge import
    assets = c.get("/api/models-assets").json()
    deriv = [a for a in assets if a.get("asset_type") == "derivative_checkpoint"]
    assert any(a.get("asset_id") == "deriv-test" for a in deriv)
    assert created["derivate_asset_id"] == "deriv-test"
