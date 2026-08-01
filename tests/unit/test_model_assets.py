"""Unit tests for Milestone 1: checkpoint inspection and action eligibility."""

from __future__ import annotations

from eval_lab.inspection.checkpoint import inspect_checkpoint
from eval_lab.schemas.model_asset import EnvBudget, ModelAssetRecord, ModelAssetType
from eval_lab.services.models import resolve_available_actions


def _source(path: str | None = "/models/Kimi-K3") -> ModelAssetRecord:
    """An oversized, atlas-compatible source checkpoint."""
    return ModelAssetRecord(
        asset_id="kimi-k3",
        name="Kimi K3",
        asset_type=ModelAssetType.source_checkpoint,
        path=path,
        architecture="KimiK3ForCausalLM",
        stored_size_bytes=int(1.5 * 1024**4),
        resident_estimate_bytes=int(1.5 * 1024**4),
        runnable=False,
        atlas_compatible=True,
        validation_state="valid",
    )


def _runnable() -> ModelAssetRecord:
    return ModelAssetRecord(
        asset_id="llama",
        name="My Runnable",
        asset_type=ModelAssetType.runnable_local,
        path="/runnable/llama",
        runnable=True,
        validation_state="valid",
    )


def test_oversized_source_eligibility(tmp_path) -> None:
    ck = tmp_path / "Kimi-K3"
    ck.mkdir()
    acts = resolve_available_actions(_source(str(ck)))
    assert acts["evaluate_directly"].available is False
    assert "no runnable endpoint" in acts["evaluate_directly"].reason
    assert acts["build_atlas"].available is True
    assert acts["inspect_checkpoint"].available is True
    assert acts["create_keep_map"].available is False
    assert "No completed atlas run" in acts["create_keep_map"].reason


def test_runnable_eligibility() -> None:
    acts = resolve_available_actions(_runnable())
    assert acts["evaluate_directly"].available is True
    # Runnable local model is not a source checkpoint -> atlas unavailable.
    assert acts["build_atlas"].available is False


def test_keep_map_enabled_when_atlas_exists() -> None:
    asset = _source()
    # A source checkpoint with a completed atlas attached unlocks keep-map.
    asset = asset.model_copy(update={"source_atlas_run_id": "atlas-1"})
    acts = resolve_available_actions(asset)
    assert acts["create_keep_map"].available is True
    assert acts["create_experiment"].available is True


def test_compare_gated_on_eval() -> None:
    acts = resolve_available_actions(_source(), EnvBudget(has_completed_eval=True))
    assert acts["compare"].available is True
    # Without any completed evaluation there is nothing to compare.
    assert resolve_available_actions(_source())["compare"].available is False


def test_remote_endpoint_evaluable_without_path() -> None:
    asset = ModelAssetRecord(
        asset_id="dsv4",
        name="DeepSeek V4",
        asset_type=ModelAssetType.remote_endpoint,
        runnable=True,
        validation_state="valid",
    )
    acts = resolve_available_actions(asset)
    assert acts["evaluate_directly"].available is True
    # No local directory -> not inspectable.
    assert acts["inspect_checkpoint"].available is False
    assert acts["inspect_checkpoint"].reason is not None


# ---------------------------------------------------------------------------
# checkpoint inspection
# ---------------------------------------------------------------------------


def test_inspection_classifies_sparse_checkpoint(mini_checkpoint) -> None:
    ins = inspect_checkpoint(mini_checkpoint, memory_gb=256)
    assert ins.valid is True
    assert ins.atlas_compatible is True
    assert ins.num_hidden_layers == 93
    assert ins.num_local_experts == 896
    assert ins.num_experts_per_tok == 16
    assert ins.architecture == "KimiK3ForCausalLM"
    assert ins.shard_count == 2
    assert ins.stored_size_bytes > 0
    # Tiny synthetic tensors fit the envelope.
    assert ins.runnable_here is True


def test_inspection_non_directory_invalid() -> None:
    ins = inspect_checkpoint("/no/such/dir")
    assert ins.valid is False
    assert any(i.level == "error" for i in ins.issues)


def test_inspection_missing_config_invalid(tmp_path) -> None:
    d = tmp_path / "bare"
    d.mkdir()
    ins = inspect_checkpoint(d)
    assert ins.valid is False
    assert any("config.json not found" in i.message for i in ins.issues)


def test_inspection_tiny_memory_budget_disables_running(mini_checkpoint) -> None:
    # If the available budget is tiny, the same checkpoint is not runnable-here.
    ins = inspect_checkpoint(mini_checkpoint, memory_gb=0.0001)
    assert ins.runnable_here is False
