"""Unit tests for the Phase 4 advanced scorers (spec 13.3)."""

from __future__ import annotations

import json
from pathlib import Path

from eval_lab.schemas.models import ScoreResult
from eval_lab.scorers.aggregate import aggregate
from eval_lab.scorers.artifact import ArtifactScorer
from eval_lab.scorers.base import available_scorers, get_scorer
from eval_lab.scorers.trajectory import TrajectoryScorer
from eval_lab.scorers.unit_test import UnitTestScorer
from eval_lab.scorers.visual import VisualScorer


def _write_trace(run_dir: Path, events: list[dict[str, object]]) -> None:
    lines = [
        json.dumps(
            {
                "schema_version": "1.0",
                "run_id": "r",
                "sequence": i,
                "time_monotonic_ns": i,
                "event_type": e["event_type"],
                "span_id": None,
                "parent_span_id": None,
                "payload": e["payload"],
            }
        )
        for i, e in enumerate(events)
    ]
    (run_dir / "trace.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _events(*pairs: tuple[str, bool]) -> list[dict[str, object]]:
    return [{"event_type": "tool_result", "payload": {"tool": t, "ok": ok}} for t, ok in pairs]


# ---------------------------------------------------------------------------
# registration
# ---------------------------------------------------------------------------


def test_available_scorers_includes_advanced():
    ids = set(available_scorers())
    assert {"unit_test", "artifact", "trajectory", "visual"} <= ids


def test_get_scorer_instantiates():
    s = get_scorer("unit_test")
    assert s(command="true").scorer_id == "unit_test"


# ---------------------------------------------------------------------------
# unit_test
# ---------------------------------------------------------------------------


def test_unit_test_pass():
    r = UnitTestScorer("exit 0").score(output="")
    assert r.score == 1.0 and r.passed and r.details["exit_code"] == 0


def test_unit_test_fail():
    r = UnitTestScorer("exit 3").score(output="")
    assert r.score == 0.0 and not r.passed and r.details["exit_code"] == 3


def test_unit_test_uses_workspace(tmp_path):
    (tmp_path / "flag.txt").write_text("x", encoding="utf-8")
    r = UnitTestScorer("test -f flag.txt", workspace=str(tmp_path)).score(output="")
    assert r.passed and r.score == 1.0


def test_unit_test_setup_error_not_silent_zero(tmp_path):
    bad = tmp_path / "does-not-exist"
    r = UnitTestScorer("true", workspace=str(bad)).score(output="")
    assert r.error is not None  # setup failure => error, never a silent zero


# ---------------------------------------------------------------------------
# artifact
# ---------------------------------------------------------------------------


def test_artifact_exists(tmp_path):
    p = tmp_path / "out.bin"
    p.write_bytes(b"hello world")
    r = ArtifactScorer("out.bin").score(output="", run_dir=tmp_path)
    assert r.passed and r.score == 1.0 and r.details["exists"]


def test_artifact_hash_and_min_size(tmp_path):
    p = tmp_path / "out.bin"
    data = b"hello world"
    p.write_bytes(data)
    import hashlib

    digest = hashlib.sha256(data).hexdigest()
    r = ArtifactScorer("out.bin", hash=digest, min_size=5).score(output="", run_dir=tmp_path)
    assert r.passed and r.score == 1.0


def test_artifact_missing_is_legit_zero_not_error(tmp_path):
    r = ArtifactScorer("nope.bin").score(output="", run_dir=tmp_path)
    assert r.score == 0.0 and not r.passed and r.error is None


def test_artifact_hash_mismatch_is_legit_zero(tmp_path):
    (tmp_path / "out.bin").write_bytes(b"hello world")
    r = ArtifactScorer("out.bin", hash="0" * 64).score(output="", run_dir=tmp_path)
    assert r.score == 0.0 and not r.passed and r.error is None


def test_artifact_min_size_failure(tmp_path):
    (tmp_path / "out.bin").write_bytes(b"hi")
    r = ArtifactScorer("out.bin", min_size=10).score(output="", run_dir=tmp_path)
    assert r.score == 0.0 and r.details["failures"] == ["size 2 < min_size 10"]


# ---------------------------------------------------------------------------
# trajectory
# ---------------------------------------------------------------------------


def test_trajectory_good_passes(tmp_path):
    events = [
        {"event_type": "agent_turn_start", "payload": {"turn": 0}},
        {"event_type": "model_completion", "payload": {"finish_reason": "stop"}},
    ] + _events(("file_read", True), ("file_write", True), ("file_read", True))
    _write_trace(tmp_path, events)
    r = TrajectoryScorer().score(output="", run_dir=tmp_path)
    assert r.passed and r.score == 1.0
    assert r.details["skipped_dimensions"] == ["repeats_failed_action", "recovery"]


def test_trajectory_bad_fails(tmp_path):
    events = [
        {"event_type": "model_completion", "payload": {"finish_reason": "stop"}},
    ] + _events(
        ("file_read", False),
        ("file_read", False),
        ("file_read", False),
        ("file_write", True),
        ("file_write", False),
        ("file_write", False),
    )
    _write_trace(tmp_path, events)
    r = TrajectoryScorer().score(output="", run_dir=tmp_path)
    assert not r.passed and r.score < 0.6
    dims = r.details["dimensions"]
    assert abs(dims["repeats_failed_action"]["score"] - 0.4) < 1e-6
    assert abs(dims["recovery"]["score"] - 0.2) < 1e-6


def test_trajectory_pass_threshold_adjusts(tmp_path):
    events = [
        {"event_type": "model_completion", "payload": {"finish_reason": "stop"}},
    ] + _events(
        ("file_read", False),
        ("file_read", False),
        ("file_read", False),
        ("file_write", True),
        ("file_write", False),
        ("file_write", False),
    )
    _write_trace(tmp_path, events)
    r = TrajectoryScorer(pass_threshold=0.5).score(output="", run_dir=tmp_path)
    assert r.passed and r.score >= 0.5


def test_trajectory_missing_trace_errors(tmp_path):
    r = TrajectoryScorer().score(output="", run_dir=tmp_path)
    assert r.error is not None  # cannot score => error, not a silent zero


def test_trajectory_no_evidence_errors(tmp_path):
    _write_trace(
        tmp_path,
        [{"event_type": "run_start", "payload": {"task_id": "t"}}],
    )
    r = TrajectoryScorer().score(output="", run_dir=tmp_path)
    assert r.error is not None  # no trajectory evidence => cannot score


# ---------------------------------------------------------------------------
# visual
# ---------------------------------------------------------------------------


def test_visual_scene_counts_meets_bounds(tmp_path):
    (tmp_path / "artifacts").mkdir(exist_ok=True)
    scene = {
        "objects": [
            {"type": "cube", "x": 0, "y": 0, "z": 0, "length": 1, "width": 1, "height": 1},
            {"type": "sphere", "x": 5, "y": 5, "z": 5, "radius": 1},
        ]
    }
    (tmp_path / "artifacts" / "scene.json").write_text(json.dumps(scene), encoding="utf-8")
    r = VisualScorer(
        "json_scene",
        expected={
            "object_counts": {"cube": 1, "sphere": 1},
            "bounds": {"x": [-10, 10], "y": [-10, 10], "z": [-10, 10]},
            "collision": {"min_separation": 1.0},
        },
    ).score(output="", run_dir=tmp_path)
    assert r.passed and r.score == 1.0


def test_visual_scene_collision_fails(tmp_path):
    (tmp_path / "artifacts").mkdir(exist_ok=True)
    scene = {
        "objects": [
            {"type": "cube", "x": 0, "y": 0, "z": 0, "length": 1, "width": 1, "height": 1},
            {"type": "cube", "x": 0.1, "y": 0, "z": 0, "length": 1, "width": 1, "height": 1},
        ]
    }
    (tmp_path / "artifacts" / "scene.json").write_text(json.dumps(scene), encoding="utf-8")
    r = VisualScorer("json_scene", expected={"collision": {"min_separation": 1.0}}).score(
        output="", run_dir=tmp_path
    )
    assert not r.passed and r.score < 1.0
    assert any(not c["passed"] for c in r.details["checks"])


def test_visual_scene_missing_required_is_error(tmp_path):
    (tmp_path / "artifacts").mkdir(exist_ok=True)
    r = VisualScorer("json_scene", required=True).score(output="", run_dir=tmp_path)
    assert r.error is not None  # missing scene, required => cannot score


def test_visual_json_scene_not_required_is_zero(tmp_path):
    (tmp_path / "artifacts").mkdir(exist_ok=True)
    r = VisualScorer("json_scene", required=False).score(output="", run_dir=tmp_path)
    assert r.score == 0.0 and not r.passed and r.error is None


def test_visual_image_exact(tmp_path):
    (tmp_path / "out.png").write_bytes(b"data")
    (tmp_path / "ref.png").write_bytes(b"data")
    r = VisualScorer("image", produced="out.png", reference="ref.png", method="exact").score(
        output="", run_dir=tmp_path
    )
    assert r.passed and r.score == 1.0


def test_visual_image_diff(tmp_path):
    (tmp_path / "out.png").write_bytes(b"abcdefgh")
    (tmp_path / "ref.png").write_bytes(b"abcdeXgh")
    r = VisualScorer("image", produced="out.png", reference="ref.png", method="diff").score(
        output="", run_dir=tmp_path
    )
    # 1 differing byte of 8 => 1 - 1/8 = 0.875
    assert abs(r.score - 0.875) < 1e-9


def test_visual_image_missing_required_errors(tmp_path):
    r = VisualScorer("image", produced="out.png", reference="ref.png", required=True).score(
        output="", run_dir=tmp_path
    )
    assert r.error is not None


def test_visual_image_missing_not_required_zero(tmp_path):
    r = VisualScorer("image", produced="out.png", reference="ref.png", required=False).score(
        output="", run_dir=tmp_path
    )
    assert r.score == 0.0 and not r.passed and r.error is None


# ---------------------------------------------------------------------------
# aggregate never zeros an errored scorer
# ---------------------------------------------------------------------------


def test_aggregate_excludes_errored_scorer_never_zero():
    errored = ScoreResult(scorer_id="unit_test", score=0.0, passed=False, error="setup failure")
    good = ScoreResult(scorer_id="exact", score=1.0, passed=True)
    agg = aggregate([errored, good], weights={"unit_test": 1.0, "exact": 1.0})
    assert agg.weight_sum == 1.0  # errored excluded, not a zero
    assert agg.total == 1.0
    assert agg.passed
