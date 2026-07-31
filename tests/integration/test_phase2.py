"""Phase 2 tests: agent loop, tool dispatch, workspace hashing, escape safety."""

from __future__ import annotations

from pathlib import Path

import pytest

from eval_lab.adapters.scripted import ScriptedToolAdapter
from eval_lab.runners.agent import run_agent
from eval_lab.sandboxes.base import (
    LocalProcessSandbox,
    build_sandbox,
)
from eval_lab.storage.artifacts import fingerprint_dir
from eval_lab.tools.protocol import (
    available_tools,
    get_tool,
)


def _sandbox_ws(tmp_path: Path, files: dict[str, str]) -> str:
    ws = tmp_path / "ws"
    ws.mkdir(exist_ok=True)
    for name, content in files.items():
        p = ws / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return str(ws)


def test_agent_loop_writes_file_and_answers(tmp_path):
    sandbox = LocalProcessSandbox()
    sandbox.prepare()
    adapter = ScriptedToolAdapter(
        [
            {"tool": "file_write", "args": {"path": "out.txt", "content": "hello agent"}},
            {"answer": "done"},
        ]
    )
    run = run_agent(
        adapter,
        prompt="write out.txt then stop",
        system_prompt=None,
        sandbox=sandbox,
        max_turns=10,
    )
    assert run.status == "completed"
    assert run.final_answer == "done"
    assert len(run.turns) == 1
    # The file was created inside the workspace by the agent's tool call.
    assert (Path(sandbox.workspace_path()) / "out.txt").read_text() == "hello agent"
    sandbox.destroy()


def test_agent_loop_surfaces_unknown_tool(tmp_path):
    sandbox = LocalProcessSandbox()
    sandbox.prepare()
    adapter = ScriptedToolAdapter(
        [
            {"tool": "nonexistent_tool", "args": {}},
            {"answer": "ok"},
        ]
    )
    run = run_agent(adapter, prompt="p", system_prompt=None, sandbox=sandbox, max_turns=10)
    # The unknown tool becomes an observation but the loop continues to a final answer.
    assert run.status == "completed"
    assert run.final_answer == "ok"
    obs = run.turns[0].observations[0]
    assert obs.ok is False
    assert "unknown tool" in (obs.error or "")
    sandbox.destroy()


def test_agent_loop_budget_max_turns(tmp_path):
    sandbox = LocalProcessSandbox()
    sandbox.prepare()
    # Always issue a shell tool call -> never reaches a final answer.
    adapter = ScriptedToolAdapter([{"tool": "shell", "args": {"command": "true"}}] * 100)
    run = run_agent(adapter, prompt="p", system_prompt=None, sandbox=sandbox, max_turns=3)
    assert run.status == "budget"
    sandbox.destroy()


def test_workspace_escape_is_blocked(tmp_path):
    sandbox = LocalProcessSandbox()
    sandbox.prepare()
    # Attempt to write outside the workspace via a path escape.
    adapter = ScriptedToolAdapter(
        [
            {"tool": "file_write", "args": {"path": "../../escape.txt", "content": "nope"}},
            {"answer": "done"},
        ]
    )
    run = run_agent(adapter, prompt="p", system_prompt=None, sandbox=sandbox, max_turns=10)
    obs = run.turns[0].observations[0]
    assert obs.ok is False  # escape must fail safely
    assert "escape" in (obs.error or "").lower() or "not allowed" in (obs.error or "").lower()
    # No file was created outside the workspace.
    assert not (tmp_path / "escape.txt").exists()
    assert not (Path(sandbox.workspace_path()) / ".." / "escape.txt").exists()
    sandbox.destroy()


def test_workspace_hash_detects_change(tmp_path):
    ws = _sandbox_ws(tmp_path, {"a.txt": "one"})
    h1 = fingerprint_dir(ws)
    Path(ws, "a.txt").write_text("changed")
    h2 = fingerprint_dir(ws)
    assert h1 != h2
    assert h1 != "MISSING"


def test_tool_registry_has_all_tools():
    names = available_tools()
    for expected in ("shell", "file_read", "file_write", "list_files"):
        assert expected in names
        assert get_tool(expected) is not None


def test_build_sandbox_unknown_raises():
    with pytest.raises(ValueError):
        build_sandbox("blaster", {})


def test_docker_missing_binary(tmp_path):
    # If docker is absent, prepare() should raise (graceful), not crash.
    if docker := build_sandbox("docker", {"image": "x"}):
        with pytest.raises(RuntimeError):
            docker.prepare()
