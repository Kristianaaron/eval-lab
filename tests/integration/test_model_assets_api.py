"""Integration tests for Milestone 1 model-asset service + API contracts."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from eval_lab.dashboard import create_app  # noqa: E402
from eval_lab.schemas.model_asset import ModelAssetType  # noqa: E402
from eval_lab.services.models import ModelAssetService  # noqa: E402


def _client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(tmp_path / "runs", models_root=tmp_path / "models"))


def test_fixtures_seeded_on_first_start(tmp_path: Path) -> None:
    c = _client(tmp_path)
    assets = c.get("/api/models-assets").json()
    ids = {a["asset_id"] for a in assets}
    assert {"kimi-k3-official", "deepseek-v4-flash", "qwen3.5-2b-vision", "k3-agent-96"} <= ids


def test_detail_includes_eligibility(tmp_path: Path) -> None:
    c = _client(tmp_path)
    detail = c.get("/api/models-assets/kimi-k3-official").json()
    assert detail["record"]["asset_type"] == "source_checkpoint"
    acts = detail["actions"]["actions"]
    assert acts["build_atlas"]["available"] is True
    assert acts["evaluate_directly"]["available"] is False
    assert "no runnable endpoint" in acts["evaluate_directly"]["reason"]


def test_actions_endpoint_and_404(tmp_path: Path) -> None:
    c = _client(tmp_path)
    assert c.get("/api/models-assets/kimi-k3-official/actions").status_code == 200
    assert c.get("/api/models-assets/does-not-exist").status_code == 404
    assert c.get("/api/models-assets/does-not-exist/actions").status_code == 404


def test_inspect_endpoint(tmp_path: Path, mini_checkpoint: Path) -> None:
    c = _client(tmp_path)
    r = c.post("/api/models-assets/inspect", json={"path": str(mini_checkpoint)})
    assert r.status_code == 200
    ins = r.json()["inspection"]
    assert ins["atlas_compatible"] is True
    assert r.json()["recommend_atlas"] is True


def test_register_persists_and_reloads(tmp_path: Path, mini_checkpoint: Path) -> None:
    c = _client(tmp_path)
    r = c.post("/api/models-assets", json={"path": str(mini_checkpoint), "name": "Mini K3"})
    assert r.status_code == 200
    asset_id = r.json()["record"]["asset_id"]
    assert r.json()["record"]["validation_state"] == "valid"

    # Persisted: a fresh store (same root) can read it back.
    again = ModelAssetService(tmp_path / "models").get_model_asset(asset_id)
    assert again is not None
    assert again.name == "Mini K3"

    # Confirm it appears in the list endpoint.
    found = [a for a in c.get("/api/models-assets").json() if a["asset_id"] == asset_id]
    assert len(found) == 1


def test_register_invalid_path_records_invalid(tmp_path: Path) -> None:
    c = _client(tmp_path)
    r = c.post("/api/models-assets", json={"path": "/nonexistent/path"})
    assert r.status_code == 200
    assert r.json()["record"]["validation_state"] == "invalid"
    # Path is not a real directory -> re-inspect action disabled with a reason.
    assert r.json()["actions"]["actions"]["inspect_checkpoint"]["available"] is False
    assert r.json()["actions"]["actions"]["inspect_checkpoint"]["reason"] is not None


def test_delete_asset(tmp_path: Path) -> None:
    c = _client(tmp_path)
    # Delete the seeded kimi asset.
    assert c.delete("/api/models-assets/kimi-k3-official").status_code == 200
    assert c.get("/api/models-assets/kimi-k3-official").status_code == 404
    assert c.delete("/api/models-assets/kimi-k3-official").status_code == 404


def test_registered_type_derives_from_inspection(tmp_path: Path, mini_checkpoint: Path) -> None:
    c = _client(tmp_path)
    r = c.post("/api/models-assets", json={"path": str(mini_checkpoint)})
    rec = r.json()["record"]
    # Sparse, atlas-compatible -> classified as a source checkpoint.
    assert rec["asset_type"] == ModelAssetType.source_checkpoint.value
