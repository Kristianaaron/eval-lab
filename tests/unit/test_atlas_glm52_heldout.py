from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from eval_lab.adapters.base import GenerationRequest, GenerationResult, HealthStatus, ModelMetadata
from eval_lab.adapters.openai_compatible import OpenAICompatibleAdapter
from eval_lab.cli.main import app
from eval_lab.runners.direct import DirectRunner, RunContext
from eval_lab.tasks.loader import TaskLoadError, load_task_yaml

ROOT = Path(__file__).parents[2]
TASKS = ROOT / "tasks"
SUITE = ROOT / "configs" / "suites" / "atlas-glm52-heldout.yaml"


class CapturingAdapter:
    def __init__(self) -> None:
        self.requests: list[GenerationRequest] = []

    def healthcheck(self) -> HealthStatus:
        return HealthStatus()

    def metadata(self) -> ModelMetadata:
        return ModelMetadata()

    def generate(self, request: GenerationRequest) -> GenerationResult:
        self.requests.append(request)
        if "23 + 28" in request.prompt:
            text = "51"
        elif "cobalt" in request.prompt:
            text = "6"
        else:
            text = "Tuesday"
        return GenerationResult(text=text)


def test_heldout_cli_binds_prompt_parameters_and_manifest(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    adapter = CapturingAdapter()
    monkeypatch.setattr("eval_lab.cli.main._build_model", lambda *_args: adapter)

    result = CliRunner().invoke(
        app,
        [
            "run",
            "suite",
            str(SUITE),
            "--model",
            "glm52-candidate",
            "--endpoint",
            "http://127.0.0.1:8080/v1",
            "--model-name",
            "glm-5.2",
            "--tasks-dir",
            str(TASKS),
            "--runs-root",
            str(tmp_path / "runs"),
            "--db",
            str(tmp_path / "runstore.db"),
            "--seed",
            "17",
            "--temperature",
            "0.0",
            "--max-tokens",
            "96",
            "--http-timeout-seconds",
            "45",
            "--task-timeout-seconds",
            "300",
            "--require-held-out",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    assert len(adapter.requests) == 9
    assert {request.prompt for request in adapter.requests} >= {
        "What is 23 + 28? Reply with only the decimal answer.\n",
        'How many letters are in the word "cobalt"? Reply with only the decimal answer.\n',
        "If today is Monday, what day comes next? Reply with only the day name.\n",
    }
    for request in adapter.requests:
        assert request.seed == 17
        assert request.temperature == 0.0
        assert request.max_tokens == 96
        assert request.timeout_seconds == 45.0
    manifests = list((tmp_path / "runs").glob("*/manifest.json"))
    assert len(manifests) == 9
    for path in manifests:
        manifest = json.loads(path.read_text())
        assert manifest["random_seed"] == 17
        assert manifest["sampling"] == {"temperature": 0.0, "max_tokens": 96}
        assert manifest["budgets"] == {"timeout_seconds": 300.0, "http_timeout_seconds": 45.0}


def test_heldout_mode_rejects_unpartitioned_task(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        app,
        [
            "run",
            "task",
            "mathematics.basic.addition.001",
            "--tasks-dir",
            str(TASKS),
            "--runs-root",
            str(tmp_path / "runs"),
            "--db",
            str(tmp_path / "runstore.db"),
            "--task-timeout-seconds",
            "300",
            "--require-held-out",
        ],
    )
    assert result.exit_code != 0
    assert "held_out_evaluation" in result.output


def test_task_loader_rejects_escape_and_symlink_assets(tmp_path: Path) -> None:
    base = """\
id: atlas.test.asset.001
name: asset
description: asset
input: {instruction_file: %s}
execution: {runner: direct}
"""
    outside = tmp_path / "outside.md"
    outside.write_text("outside")
    escaped = tmp_path / "task.yaml"
    escaped.write_text(base % "../outside.md")
    with pytest.raises(TaskLoadError, match="package-relative"):
        load_task_yaml(escaped)
    linked = tmp_path / "linked.md"
    os.symlink(outside, linked)
    escaped.write_text(base % "linked.md")
    with pytest.raises(TaskLoadError, match="symlinks"):
        load_task_yaml(escaped)


def test_openai_adapter_uses_bound_request_timeout_and_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class Response:
        status = 200

        def __enter__(self) -> Response:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self) -> bytes:
            return b'{"choices":[{"message":{"content":"ok"},"finish_reason":"stop"}]}'

    def fake_urlopen(request: object, *, timeout: float) -> Response:
        captured["timeout"] = timeout
        captured["payload"] = json.loads(request.data.decode())  # type: ignore[attr-defined]
        return Response()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    request = GenerationRequest(
        "exact package prompt",
        temperature=0.0,
        max_tokens=96,
        seed=17,
        timeout_seconds=3.5,
    )
    result = OpenAICompatibleAdapter("http://127.0.0.1/v1", "glm").generate(request)
    assert result.error is None
    assert captured["timeout"] == 3.5
    assert captured["payload"]["messages"] == [{"role": "user", "content": "exact package prompt"}]
    assert captured["payload"]["seed"] == 17
    assert captured["payload"]["temperature"] == 0.0
    assert captured["payload"]["max_tokens"] == 96


def test_direct_runner_fails_closed_after_task_deadline(tmp_path: Path) -> None:
    task = load_task_yaml(TASKS / "atlas_glm52_heldout" / "math_sum" / "task.yaml")

    class SlowAdapter(CapturingAdapter):
        def generate(self, request: GenerationRequest) -> GenerationResult:
            time.sleep(0.01)
            return super().generate(request)

    result = DirectRunner().execute_task(
        task,
        RunContext(
            task=task,
            model=SlowAdapter(),
            model_id="candidate",
            task_timeout_seconds=0.001,
            runs_root=str(tmp_path / "runs"),
        ),
    )
    assert result.status == "error"
    assert result.error == "task timeout exceeded"
    assert result.aggregate is None
