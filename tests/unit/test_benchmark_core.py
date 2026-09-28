"""Tests for the standalone-benchmark core: task input resolution, native tool
calling, agent scoring inside the sandbox, perplexity and hidden-test scoring."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pytest

from eval_lab.adapters.base import GenerationRequest, GenerationResult, LogprobModelAdapter
from eval_lab.adapters.mock import MockModelAdapter
from eval_lab.adapters.openai_compatible import OpenAICompatibleAdapter, _parse_logprobs
from eval_lab.adapters.scripted import ScriptedToolAdapter
from eval_lab.runners.agent import run_agent, tool_definitions
from eval_lab.runners.agent_executor import AgentRunner
from eval_lab.runners.direct import DirectRunner, RunContext
from eval_lab.runners.dispatch import runner_for
from eval_lab.runners.perplexity import PerplexityRunner, compute_metrics, windows
from eval_lab.sandboxes.base import LocalProcessSandbox
from eval_lab.scorers.python_tests import PythonTestsScorer, extract_python
from eval_lab.storage.sqlite import RunStore
from eval_lab.tasks.loader import load_task_yaml
from eval_lab.tasks.resolve import build_prompt, fixture_dir

REPO = Path(__file__).resolve().parents[2]
TASKS = REPO / "tasks"


# -- task input resolution --------------------------------------------------


def test_loader_records_source_dir_and_prompt_includes_attachments() -> None:
    task = load_task_yaml(TASKS / "long_context" / "log_analysis" / "task.yaml")
    assert task.source_dir == str((TASKS / "long_context" / "log_analysis").resolve())
    prompt = build_prompt(task)
    assert prompt.startswith("Read the attached event log")
    assert "## Attachment: data/events.log" in prompt
    assert "WARN" in prompt
    # The persisted contract is unchanged (private attr is not dumped).
    assert "source_dir" not in task.model_dump()


def test_fixture_dir_resolves_relative_to_task_package() -> None:
    task = load_task_yaml(TASKS / "agentic" / "multi_file_fix" / "task.yaml")
    fixture = fixture_dir(task)
    assert fixture is not None and (fixture / "tests" / "run_all.py").is_file()


def test_direct_runner_sends_real_prompt_not_filename(tmp_path: Path) -> None:
    task = load_task_yaml(TASKS / "long_context" / "log_analysis" / "task.yaml")
    seen: list[str] = []

    class Spy(MockModelAdapter):
        def generate(self, request: GenerationRequest | str) -> GenerationResult:
            assert isinstance(request, GenerationRequest)
            seen.append(request.prompt)
            return GenerationResult(text="4")

    result = DirectRunner().execute_task(
        task, RunContext(task=task, model=Spy(), model_id="spy", runs_root=str(tmp_path))
    )
    assert seen and seen[0] != "prompt.md" and "Attachment" in seen[0]
    assert result.aggregate is not None and result.aggregate.passed


def test_dispatch_picks_runner_from_spec() -> None:
    assert (
        type(
            runner_for(load_task_yaml(TASKS / "agentic" / "multi_file_fix" / "task.yaml"))
        ).__name__
        == "AgentRunner"
    )
    assert (
        type(
            runner_for(load_task_yaml(TASKS / "long_context" / "log_analysis" / "task.yaml"))
        ).__name__
        == "DirectRunner"
    )


# -- native tool calling ------------------------------------------------------


class RecordingAdapter(ScriptedToolAdapter):
    def __init__(self, script: list[dict[str, Any]]) -> None:
        super().__init__(script)
        self.requests: list[GenerationRequest] = []

    def generate(self, request: GenerationRequest) -> GenerationResult:
        self.requests.append(request)
        return super().generate(request)


def test_agent_loop_advertises_tools_and_keeps_tool_messages() -> None:
    sandbox = LocalProcessSandbox()
    sandbox.prepare()
    adapter = RecordingAdapter(
        [
            {"id": "c1", "tool": "file_write", "args": {"path": "a.txt", "content": "x"}},
            {"id": "c2", "tool": "shell", "args": {"command": "cat a.txt"}},
            {"answer": "done"},
        ]
    )
    run = run_agent(adapter, prompt="p", system_prompt=None, sandbox=sandbox, max_turns=5)
    sandbox.destroy()
    assert run.status == "completed" and run.tool_call_count == 2
    first = adapter.requests[0]
    assert first.tools and {t["function"]["name"] for t in first.tools} >= {"shell", "file_write"}
    assert first.system_prompt  # default agent system prompt is supplied
    last = adapter.requests[-1].messages
    roles = [m["role"] for m in last]
    # The final assistant answer is appended to the same history after the call.
    assert roles == ["user", "assistant", "tool", "assistant", "tool", "assistant"]
    assert last[1]["tool_calls"][0]["id"] == "c1"
    assert last[2]["tool_call_id"] == "c1" and "wrote" in last[2]["content"]
    assert last[4]["content"].startswith("x")


def test_tool_definitions_respect_allowlist() -> None:
    names = {d["function"]["name"] for d in tool_definitions(["shell"])}
    assert names == {"shell"}


def test_openai_adapter_sends_tools_and_parses_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: dict[str, Any] = {}

    def fake_post(self: Any, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        sent["path"] = path
        sent["payload"] = payload
        return {
            "choices": [
                {
                    "finish_reason": "tool_calls",
                    "message": {
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "type": "function",
                                "function": {"name": "shell", "arguments": '{"command": "ls"}'},
                            }
                        ],
                    },
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }

    monkeypatch.setattr(OpenAICompatibleAdapter, "_post", fake_post)
    adapter = OpenAICompatibleAdapter("http://x/v1", "m")
    res = adapter.generate(GenerationRequest(prompt="hi", tools=tool_definitions()))
    assert sent["path"] == "/chat/completions"
    assert sent["payload"]["tools"] and sent["payload"]["tool_choice"] == "auto"
    assert "tools" not in json.dumps(sent["payload"]).replace('"tools": [', "")  # no null tools
    assert res.tool_calls[0].name == "shell" and res.tool_calls[0].arguments == {"command": "ls"}
    assert res.finish_reason == "tool_calls"


# -- agent executor scores inside the sandbox ---------------------------------


def _write_agent_task(root: Path) -> Path:
    pkg = root / "agentic" / "fixme"
    (pkg / "workspace" / "tests").mkdir(parents=True)
    (pkg / "workspace" / "tests" / "__init__.py").write_text("")
    (pkg / "workspace" / "calc.py").write_text("def add(a, b):\n    return a - b\n")
    (pkg / "workspace" / "tests" / "test_calc.py").write_text(
        "import unittest\nfrom calc import add\n\nclass T(unittest.TestCase):\n"
        "    def test_add(self):\n        self.assertEqual(add(2, 3), 5)\n"
        "    def test_neg(self):\n        self.assertEqual(add(-1, 1), 0)\n"
    )
    (pkg / "hidden" / "tests").mkdir(parents=True)
    (pkg / "hidden" / "tests" / "test_hidden.py").write_text(
        "import unittest\nfrom calc import add\n\nclass H(unittest.TestCase):\n"
        "    def test_big(self):\n        self.assertEqual(add(10**6, 1), 10**6 + 1)\n"
        "    def test_float(self):\n        self.assertAlmostEqual(add(0.1, 0.2), 0.3)\n"
    )
    (pkg / "prompt.md").write_text("Fix calc.add so the tests pass.")
    (pkg / "task.yaml").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "id": "agentic.fixme.001",
                "name": "fix add",
                "description": "d",
                "labels": {"domains": ["coding"], "modalities": ["code"]},
                "input": {"instruction_file": "prompt.md", "workspace_fixture": "workspace"},
                "execution": {"runner": "agent", "timeout_seconds": 60, "max_turns": 6},
                "oracle": [
                    {
                        "type": "unit_test",
                        "required": True,
                        "config": {
                            "command": "python -m unittest discover -s tests -t .",
                            "timeout_seconds": 60,
                        },
                    },
                    {
                        "type": "python_tests",
                        "weight": 2.0,
                        "config": {"tests": "hidden/tests", "mode": "workspace"},
                    },
                ],
            }
        )
    )
    return pkg / "task.yaml"


def test_agent_runner_seeds_fixture_and_scores_in_workspace(tmp_path: Path) -> None:
    task = load_task_yaml(_write_agent_task(tmp_path / "tasks"))
    adapter = ScriptedToolAdapter(
        [
            {"tool": "file_read", "args": {"path": "calc.py"}},
            {
                "tool": "file_write",
                "args": {"path": "calc.py", "content": "def add(a, b):\n    return a + b\n"},
            },
            {
                "tool": "shell",
                "args": {"command": "python -m unittest discover -s tests -t . 2>&1 | tail -1"},
            },
            {"answer": "fixed"},
        ]
    )
    store = RunStore(tmp_path / "runs.db")
    result = AgentRunner().execute_task(
        task,
        RunContext(
            task=task,
            model=adapter,
            model_id="scripted",
            runs_root=str(tmp_path / "runs"),
            store=store,
        ),
    )
    store.close()
    assert result.status == "completed", result.error
    assert result.aggregate is not None and result.aggregate.passed
    by_id = {s.scorer_id: s for s in result.scores}
    assert by_id["unit_test"].passed and by_id["unit_test"].details["exit_code"] == 0
    assert by_id["python_tests"].details["tests_passed"] == 2
    snapshot = Path(result.run_dir) / "workspace" / "calc.py"
    assert snapshot.read_text().strip().endswith("return a + b")
    assert (Path(result.run_dir) / "artifacts" / "transcript.json").is_file()
    assert result.manifest["tool_calls"] == 3


def test_agent_runner_budget_exhaustion_is_still_scored(tmp_path: Path) -> None:
    task = load_task_yaml(_write_agent_task(tmp_path / "tasks"))
    adapter = ScriptedToolAdapter([{"tool": "list_files", "args": {}} for _ in range(20)])
    result = AgentRunner().execute_task(
        task,
        RunContext(task=task, model=adapter, model_id="scripted", runs_root=str(tmp_path / "runs")),
    )
    assert result.manifest["agent_status"] == "budget"
    assert result.aggregate is not None and not result.aggregate.passed


# -- hidden tests scorer ------------------------------------------------------


def test_extract_python_prefers_largest_block() -> None:
    text = "```python\nx = 1\n```\nthen\n```py\ndef f():\n    return 42\n```"
    assert "def f" in extract_python(text)
    assert extract_python("no fences here") == "no fences here"


def test_python_tests_partial_credit(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_sol.py").write_text(
        "import unittest\nfrom solution import f\n\nclass T(unittest.TestCase):\n"
        "    def test_a(self):\n        self.assertEqual(f(1), 2)\n"
        "    def test_b(self):\n        self.assertEqual(f(2), 4)\n"
        "    def test_c(self):\n        self.assertEqual(f(-1), -2)\n"
        "    def test_d(self):\n        self.assertRaises(ValueError, f, None)\n"
    )
    scorer = PythonTestsScorer(tests="tests", min_pass_fraction=1.0)

    class T:
        source_dir = str(tmp_path)

    good = scorer.score(
        output="```python\ndef f(x):\n    if x is None: raise ValueError\n    return 2*x\n```",
        task=T(),
    )
    assert good.passed and good.score == 1.0 and good.details["tests_total"] == 4
    partial = scorer.score(output="```python\ndef f(x):\n    return 2*x\n```", task=T())
    assert not partial.passed and partial.score == 0.75
    assert partial.details["failed"][0]["id"].endswith("test_d")
    broken = scorer.score(output="```python\ndef f(x:\n```", task=T())
    assert broken.score == 0.0 and broken.details["tests_total"] == 0 and broken.error is None


# -- perplexity -----------------------------------------------------------------


def test_windows_cover_text_with_and_without_overlap() -> None:
    text = "a" * 25
    plain = windows(text, 10)
    assert [len(w) for _, w in plain] == [10, 10, 5] and all(s == 0 for s, _ in plain)
    strided = windows(text, 10, 5)
    assert strided[0][0] == 0 and all(s == 5 for s, _ in strided[1:])
    assert "".join(w[s:] for s, w in strided) == text


def test_compute_metrics_mock_is_deterministic_and_sane() -> None:
    adapter = MockModelAdapter()
    assert isinstance(adapter, LogprobModelAdapter)
    text = " ".join(f"tok{i}" for i in range(400))
    m1 = compute_metrics(adapter, text, window_chars=500)
    m2 = compute_metrics(adapter, text, window_chars=500)
    assert m1["perplexity"] == m2["perplexity"] > 1
    assert m1["tokens"] > 300 and m1["windows"] > 1
    assert math.isclose(m1["bits_per_token"], m1["mean_nll"] / math.log(2))
    assert m1["bits_per_byte"] > 0


def test_perplexity_runner_end_to_end(tmp_path: Path) -> None:
    pkg = tmp_path / "ppl"
    (pkg / "data").mkdir(parents=True)
    (pkg / "data" / "corpus.txt").write_text(" ".join(f"word{i % 50}" for i in range(2000)))
    (pkg / "prompt.md").write_text("perplexity corpus")
    (pkg / "task.yaml").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "id": "perplexity.test.001",
                "name": "ppl",
                "description": "d",
                "level": "model",
                "labels": {"domains": ["long_context"]},
                "input": {"instruction_file": "prompt.md", "attachments": ["data/corpus.txt"]},
                "execution": {"runner": "perplexity", "parameters": {"window_chars": 2000}},
                "oracle": [
                    {"type": "perplexity", "required": True, "config": {"max_perplexity": 50}}
                ],
            }
        )
    )
    task = load_task_yaml(pkg / "task.yaml")
    assert type(runner_for(task)).__name__ == "PerplexityRunner"
    store = RunStore(tmp_path / "runs.db")
    res = PerplexityRunner().execute_task(
        task,
        RunContext(
            task=task,
            model=MockModelAdapter(),
            model_id="mock",
            runs_root=str(tmp_path / "runs"),
            store=store,
        ),
    )
    assert res.status == "completed", res.error
    metrics = json.loads((Path(res.run_dir) / "metrics.json").read_text())
    assert metrics["windows"] >= 4 and metrics["perplexity"] < 50
    assert res.aggregate is not None and res.aggregate.passed and 0 < res.aggregate.total < 1
    row = store.get_run(res.run_id)
    store.close()
    assert row and row["status"] == "completed"
    assert res.manifest["metrics"]["perplexity"] == pytest.approx(metrics["perplexity"])


def test_perplexity_runner_without_logprob_support_is_an_error(tmp_path: Path) -> None:
    class NoLogprobs:
        def healthcheck(self):  # noqa: ANN202
            raise NotImplementedError

        def metadata(self):  # noqa: ANN202
            raise NotImplementedError

        def generate(self, request):  # noqa: ANN001, ANN202
            raise NotImplementedError

    pkg = tmp_path / "ppl"
    pkg.mkdir()
    (pkg / "prompt.md").write_text("some text here to score")
    (pkg / "task.yaml").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "id": "perplexity.test.002",
                "name": "ppl",
                "description": "d",
                "input": {"instruction_file": "prompt.md"},
                "execution": {"runner": "perplexity"},
                "oracle": [{"type": "perplexity"}],
            }
        )
    )
    task = load_task_yaml(pkg / "task.yaml")
    res = PerplexityRunner().execute_task(
        task,
        RunContext(task=task, model=NoLogprobs(), model_id="x", runs_root=str(tmp_path / "runs")),
    )
    assert res.status == "error" and "log-probabilities" in (res.error or "")
    assert res.aggregate is None


def test_parse_logprobs_echo_shape_drops_generated_token() -> None:
    data = {
        "choices": [
            {
                "text": "Hello world!",
                "logprobs": {
                    "tokens": ["Hello", " world", "!"],
                    "token_logprobs": [None, -1.5, -0.5],
                },
            }
        ],
        "usage": {"prompt_tokens": 2, "completion_tokens": 1},
    }
    res = _parse_logprobs(data, "Hello world")
    assert res.error is None and [t.token for t in res.tokens] == ["Hello", " world"]
    assert res.scored == [-1.5]
    missing = _parse_logprobs({"choices": [{"text": "x"}]}, "x")
    assert missing.error and "logprobs" in missing.error
