"""Integration tests for Phase 4: advanced scorers + judge calibration CLI."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from eval_lab.cli.main import app
from eval_lab.scorers.base import available_scorers

runner = CliRunner()

REPO = Path(__file__).resolve().parent.parent.parent


def test_phase4_imports():
    import eval_lab.judges.calibration  # noqa: F401
    import eval_lab.judges.pairwise  # noqa: F401
    import eval_lab.scorers.artifact  # noqa: F401
    import eval_lab.scorers.trajectory  # noqa: F401
    import eval_lab.scorers.unit_test  # noqa: F401
    import eval_lab.scorers.visual  # noqa: F401

    assert True


def test_available_scorers_phase4():
    ids = set(available_scorers())
    assert {"unit_test", "artifact", "trajectory", "visual"} <= ids


def test_offline_calibrate_judge_produces_report(tmp_path):
    result = runner.invoke(
        app,
        [
            "calibrate-judge",
            "answer_quality",
            "--offline",
            "--judges-dir",
            str(REPO / "configs" / "judges"),
            "--gold-dir",
            str(REPO / "gold" / "judge_calibration"),
            "--out-dir",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "VERDICT" in result.output
    md = tmp_path / "calibration_answer_quality_answer_quality.md"
    jp = tmp_path / "calibration_answer_quality_answer_quality.json"
    assert md.is_file() and jp.is_file()
    text = md.read_text(encoding="utf-8")
    assert "Verdict:" in text
    assert "Exact agreement" in text
    assert "Weighted kappa" in text
    assert "Malformed-output rate" in text


def test_offline_calibrate_judge_json_flag(tmp_path):
    result = runner.invoke(
        app,
        [
            "calibrate-judge",
            "answer_quality",
            "--offline",
            "--json",
            "--judges-dir",
            str(REPO / "configs" / "judges"),
            "--gold-dir",
            str(REPO / "gold" / "judge_calibration"),
        ],
    )
    assert result.exit_code == 0, result.output
    assert '"verdict"' in result.output
