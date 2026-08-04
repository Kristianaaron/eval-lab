"""Integration tests for the atlas-bridge consumer (eval-lab side).

The fixture export dir is hand-authored to match the frozen manifest contract
(§3) exactly; eval-lab must never import ``model_atlas``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from eval_lab.dashboard import create_app  # noqa: E402
from eval_lab.services.atlas_bridge import AtlasBridgeService  # noqa: E402
from eval_lab.services.models import ModelAssetService  # noqa: E402

RUN_ID = "atlas-abc123"

RUN_MANIFEST = {
    "schema_version": "atlas-bridge-v1",
    "atlas_run_id": RUN_ID,
    "source_arch": "k3-mini",
    "calibration_suite_id": "atlas_calibration",
    "evidence_level": "basic_saliency",
    "status": "completed",
    "started_at": "2026-08-04T00:00:00+00:00",
    "completed_at": "2026-08-04T00:10:00+00:00",
    "n_tasks": 42,
    "evidence_present": [
        "run_manifest.json",
        "layer_saliency.json",
        "plans.json",
    ],
    "software_revision": None,
}

LAYER_SALIENCY = [
    {
        "layer": 0,
        "expert": 3,
        "label": "code_generation",
        "mean": 0.9,
        "frequency": 0.4,
        "total_value": 2.1,
    }
]

PLANS = [
    {
        "name": "keep4-value",
        "strategy": "value",
        "keep_per_layer": 4,
        "kept_per_layer": {"0": 4},
        "resident_bytes_a": 123.0,
        "resident_bytes_b": 0.0,
        "keep_map": {
            "source_model_id": "k3-mini",
            "entries": [
                {
                    "layer_index": 0,
                    "source_expert_id": 3,
                    "keep": True,
                    "reason": "saliency",
                }
            ],
        },
        "precision": {
            "entries": [
                {
                    "layer_index": 0,
                    "source_expert_id": 3,
                    "precision": "bf16",
                    "bits": 16,
                    "reconstruction_error": 0.0,
                }
            ]
        },
    }
]

DERIVATIVE = {
    "model_asset_id": "deriv-0000000000",
    "display_name": "Kimi K3 v4 derivative",
    "asset_type": "derivative_checkpoint",
    "model_family": "k3-mini",
    "architecture": "MiniMoE",
    "checkpoint_path": "/models/derivatives/k3-v4",
    "parent_model_id": "source-asset-id",
    "source_experiment_id": None,
    "kept_per_layer": {"0": 4},
    "stored_size_bytes": 123,
    "estimated_resident_bytes": 456,
    "identity_source_slots": {"l0e0": "3"},
}


def _write_fixture_dir(root: Path, run_id: str = RUN_ID, *, derivative: bool = False) -> Path:
    run_dir = root / "atlas_runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "run_manifest.json").write_text(json.dumps(RUN_MANIFEST), encoding="utf-8")
    (run_dir / "layer_saliency.json").write_text(json.dumps(LAYER_SALIENCY), encoding="utf-8")
    (run_dir / "plans.json").write_text(json.dumps(PLANS), encoding="utf-8")
    if derivative:
        (run_dir / "derivative.json").write_text(json.dumps(DERIVATIVE), encoding="utf-8")
    return run_dir


def _client(tmp_path: Path) -> TestClient:
    return TestClient(
        create_app(
            tmp_path / "runs",
            models_root=tmp_path / "models",
            atlas_root=tmp_path,
        )
    )


def test_scan_finds_fixture_export(tmp_path: Path) -> None:
    _write_fixture_dir(tmp_path)
    bridge = AtlasBridgeService(tmp_path)
    runs = bridge.scan()
    assert [r.run_id for r in runs] == [RUN_ID]
    assert runs[0].arch == "k3-mini"
    assert runs[0].status == "completed"
    assert runs[0].evidence_present == RUN_MANIFEST["evidence_present"]


def test_import_persists_and_is_idempotent(tmp_path: Path) -> None:
    _write_fixture_dir(tmp_path)
    bridge = AtlasBridgeService(tmp_path)

    imp = bridge.import_run(RUN_ID)
    assert imp.n_plans == 1
    assert imp.has_derivative is False
    assert imp.plans[0].name == "keep4-value"
    km = imp.plans[0].keep_maps[0]
    assert km.unit_kind.value == "expert"
    assert km.top_k == 4
    assert km.entries[0].unit.source_unit_id == 3
    assert km.entries[0].saliency == 0.9
    assert km.entries[0].evidence_kind.value == "measured"

    # Persisted to <out_root>/atlas_runs/<id>/import.json.
    assert (tmp_path / "atlas_runs" / RUN_ID / "import.json").is_file()

    # Re-import is a no-op returning the existing record.
    again = bridge.import_run(RUN_ID)
    assert again.imported_at == imp.imported_at
    assert (tmp_path / "atlas_runs" / RUN_ID / "import.json").read_text(encoding="utf-8") == (
        tmp_path / "atlas_runs" / RUN_ID / "import.json"
    ).read_text(encoding="utf-8")


def test_derivative_registers_model_asset(tmp_path: Path) -> None:
    _write_fixture_dir(tmp_path, derivative=True)
    bridge = AtlasBridgeService(tmp_path, models_root=tmp_path / "models")

    imp = bridge.import_run(RUN_ID)
    assert imp.has_derivative is True

    asset = ModelAssetService(tmp_path / "models").get_model_asset(DERIVATIVE["model_asset_id"])
    assert asset is not None
    assert asset.asset_type.value == "derivative_checkpoint"
    assert asset.parent_asset_id == "source-asset-id"
    assert asset.source_atlas_run_id == RUN_ID
    assert asset.name == "Kimi K3 v4 derivative"
    assert asset.stored_size_bytes == 123
    assert asset.resident_estimate_bytes == 456

    # Idempotent: a second import does not duplicate the asset record.
    bridge.import_run(RUN_ID)
    assets = ModelAssetService(tmp_path / "models").list_model_assets()
    assert [a.asset_id for a in assets].count(DERIVATIVE["model_asset_id"]) == 1


def test_api_list_and_detail(tmp_path: Path) -> None:
    _write_fixture_dir(tmp_path, derivative=True)
    c = _client(tmp_path)

    runs = c.get("/api/atlas-bridge/runs").json()
    assert runs == [
        {
            "run_id": RUN_ID,
            "arch": "k3-mini",
            "status": "completed",
            "n_plans": 0,
            "has_derivative": True,
            "evidence_present": RUN_MANIFEST["evidence_present"],
        }
    ]

    imp = c.post("/api/atlas-bridge/import", json={"run_id": RUN_ID})
    assert imp.status_code == 200
    body = imp.json()
    assert body["n_plans"] == 1
    assert body["has_derivative"] is True
    assert body["saliency"] == LAYER_SALIENCY
    assert body["manifest"]["atlas_run_id"] == RUN_ID

    detail = c.get(f"/api/atlas-bridge/runs/{RUN_ID}")
    assert detail.status_code == 200
    assert detail.json()["plans"][0]["keep_maps"][0]["top_k"] == 4

    # Optionally post-process the persisted import in a fresh service.
    again = c.post("/api/atlas-bridge/import", json={"run_id": RUN_ID})
    assert again.json()["imported_at"] == body["imported_at"]


def test_api_import_404_when_dir_missing(tmp_path: Path) -> None:
    c = _client(tmp_path)
    assert c.post("/api/atlas-bridge/import", json={"run_id": "nope"}).status_code == 404
    assert c.get("/api/atlas-bridge/runs/nope").status_code == 404
    assert c.get("/api/atlas-bridge/runs").json() == []
