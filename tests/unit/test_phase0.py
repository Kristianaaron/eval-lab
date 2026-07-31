"""Unit tests for Phase 0: schemas, labels, loader, CLI, mock adapter."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from eval_lab.adapters.mock import MockModelAdapter
from eval_lab.cli.main import app
from eval_lab.config.labels import (
    LabelError,
    all_in,
    canonical,
    unknown,
    validate,
    validate_many,
)
from eval_lab.schemas.models import (
    SCHEMA_VERSION,
    Level,
    ModelConfig,
    RunManifest,
    ScoreResult,
    SuiteSpec,
    TaskLabels,
    TaskSpec,
    TraceEvent,
)
from eval_lab.tasks.loader import (
    TaskLoadError,
    check_fixture_references,
    load_suite_yaml,
    load_task_yaml,
)

FIXTURES = Path(__file__).parent / "fixtures"
TASKS = Path(__file__).parent.parent.parent / "tasks"

runner = CliRunner()


# ---------------------------------------------------------------------------
# Schema round-trips
# ---------------------------------------------------------------------------


def test_task_spec_roundtrip():
    task = TaskSpec(
        id="mathematics.basic.addition.001",
        name="Two-number addition",
        description="d",
        input={"instruction_file": "prompt.md"},
        execution={"runner": "direct"},
        labels=TaskLabels(domains=["mathematics"]),
    )
    dumped = task.model_dump_json()
    reloaded = TaskSpec.model_validate_json(dumped)
    assert reloaded == task
    assert reloaded.schema_version == SCHEMA_VERSION


def test_all_core_schemas_roundtrip():
    dataset = [
        TaskSpec(
            id="a.b.c.001",
            name="n",
            description="d",
            input={"instruction_file": "p.md"},
        ),
        SuiteSpec(id="suite.smoke.001", name="smoke", tasks=[{"task_id": "a.b.c.001"}]),
        ModelConfig(id="mock-m1", model_name="mock"),
        RunManifest(
            run_id="r1",
            task_id="a.b.c.001",
            task_version=1,
        ),
        ScoreResult(scorer_id="exact-v1", score=1.0, passed=True, required=True),
        TraceEvent(run_id="r1", sequence=0, time_monotonic_ns=0, event_type="model_request"),
    ]
    for model in dataset:
        reloaded = type(model).model_validate_json(model.model_dump_json())
        assert reloaded == model


def test_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        TaskSpec.model_validate(
            {
                "id": "x.y.z.001",
                "name": "n",
                "description": "d",
                "input": {"instruction_file": "p.md"},
                "unexpected_field": 1,
            }
        )


def test_rejects_invalid_id_pattern():
    with pytest.raises(ValidationError):
        TaskSpec(
            id="NoDotsAllowed",
            name="n",
            description="d",
            input={"instruction_file": "p.md"},
        )


# ---------------------------------------------------------------------------
# Label registry
# ---------------------------------------------------------------------------


def test_label_validate_known():
    assert validate("domain", "coding") == "coding"
    assert canonical("domain", "Software_Engineering") == "software_engineering"
    assert canonical("domain", "sw-eng") == "software_engineering"


def test_label_validate_unknown_raises():
    with pytest.raises(LabelError):
        validate("capability", "not_a_real_capability")


def test_label_unknown_reports_bad():
    bad = unknown("capability", ["code_editing", "bogus"])
    assert bad == ["bogus"]


def test_validate_many_aliases():
    assert validate_many("domain", ["Coding", "sw-eng"]) == ["coding", "software_engineering"]


def test_all_in_contains_known():
    domains = set(all_in("domain"))
    assert "coding" in domains
    assert "voxel" in domains


# ---------------------------------------------------------------------------
# Task loader
# ---------------------------------------------------------------------------


def test_load_valid_task():
    task = load_task_yaml(TASKS / "mathematics" / "basic_addition" / "task.yaml")
    assert task.id == "mathematics.basic.addition.001"
    assert task.level == Level.model
    assert task.labels.domains == ["mathematics"]


def test_load_missing_file_raises():
    with pytest.raises(TaskLoadError):
        load_task_yaml(TASKS / "does_not_exist.yaml")


def test_unknown_label_task_fails_validation():
    with pytest.raises(TaskLoadError):
        load_task_yaml(FIXTURES / "unknown_label.yaml")


def test_broken_fixture_detected():
    task = load_task_yaml(FIXTURES / "broken_fixture.yaml")
    # Loader itself accepts the YAML, but fixture check must flag the missing file.
    missing = check_fixture_references(task, FIXTURES)
    assert any("does-not-exist.tar.zst" in m for m in missing)


def test_load_suite():
    from tempfile import NamedTemporaryFile

    with NamedTemporaryFile("w", suffix=".yaml", delete=False) as fh:
        fh.write("id: suite.smoke.001\nname: smoke\ntasks:\n  - task_id: a.b.c.001\n")
        p = Path(fh.name)
    try:
        suite = load_suite_yaml(p)
        assert suite.id == "suite.smoke.001"
    finally:
        p.unlink()


# ---------------------------------------------------------------------------
# Mock adapter
# ---------------------------------------------------------------------------


def test_mock_adapter_is_deterministic():
    adapter = MockModelAdapter()
    req_a = adapter.generate("what is 2+2")
    req_b = adapter.generate("what is 2+2")
    req_c = adapter.generate("different prompt")
    assert req_a.text == req_b.text
    assert req_a.text != req_c.text
    assert req_a.finish_reason == "stop"


def test_mock_adapter_healthcheck():
    adapter = MockModelAdapter()
    assert adapter.healthcheck().ok is True
    assert adapter.metadata().model_name == "mock-deterministic-v1"


# ---------------------------------------------------------------------------
# CLI exit codes
# ---------------------------------------------------------------------------


def test_cli_doctor_ok():
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0, result.output


def test_cli_doctor_json():
    result = runner.invoke(app, ["doctor", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["status"] == "ok"


def test_cli_validate_valid_task():
    result = runner.invoke(
        app, ["validate", "task", str(TASKS / "mathematics" / "basic_addition" / "task.yaml")]
    )
    assert result.exit_code == 0, result.output


def test_cli_validate_invalid_task_exit_1():
    result = runner.invoke(app, ["validate", "task", str(FIXTURES / "unknown_label.yaml")])
    assert result.exit_code == 1


def test_cli_validate_unknown_kind_exit_2():
    result = runner.invoke(app, ["validate", "frobnicate", "x.yaml"])
    assert result.exit_code == 2


def test_cli_validate_missing_file_exit_1():
    result = runner.invoke(app, ["validate", "task", "no/such/file.yaml"])
    assert result.exit_code == 1


def test_cli_list_tasks_json():
    result = runner.invoke(app, ["list", "--dir", str(TASKS)])
    assert result.exit_code == 0, result.output
    assert "mathematics.basic.addition.001" in result.output
