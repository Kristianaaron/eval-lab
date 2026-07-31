"""Sandbox protocol and implementations (spec 12.1)."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from typing import Any, Protocol


class Sandbox(Protocol):
    def prepare(self) -> str:
        """Create the workspace, return its path."""
        ...

    def destroy(self) -> None: ...
    def workspace_path(self) -> str: ...
    def run_command(self, command: str, *, timeout_s: float = 30.0) -> tuple[int, str]: ...


class LocalProcessSandbox:
    """A lightweight local-process sandbox producing an isolated temp workspace.

    For smoke/unit tests and systems where Docker is unavailable. No OS-level
    isolation beyond an isolated temp directory (spec backs is explicitly a
    smoke-test backend).
    """

    def __init__(self, seed_workspace: str | None = None) -> None:
        self._seed = seed_workspace
        self._ws: str | None = None

    def prepare(self) -> str:
        self._ws = tempfile.mkdtemp(prefix="eval-lab-ws-")
        if self._seed:
            shutil.copytree(self._seed, self._ws, dirs_exist_ok=True)
        return self._ws

    def destroy(self) -> None:
        if self._ws:
            shutil.rmtree(self._ws, ignore_errors=True)
            self._ws = None

    def workspace_path(self) -> str:
        if self._ws is None:
            raise RuntimeError("sandbox not prepared")
        return self._ws

    def run_command(self, command: str, *, timeout_s: float = 30.0) -> tuple[int, str]:
        proc = subprocess.run(
            command,
            shell=True,
            cwd=self.workspace_path(),
            capture_output=True,
            text=True,
            timeout=timeout_s,
            env={**os.environ, "PYTHONHASHSEED": "0"},
        )
        return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


class DockerSandbox:
    """Docker-container sandbox (spec 12.1 production backend).

    Best-effort using ``docker run`` with an image, no network, and a mounted
    workspace. Raises RuntimeError if Docker is unavailable.
    """

    def __init__(self, image: str, *, network: str = "none") -> None:
        self.image = image
        self.network = network
        self._container: str | None = None
        self._ws: str | None = None

    def prepare(self) -> str:
        self._ws = tempfile.mkdtemp(prefix="eval-lab-docker-ws-")
        # Validate docker is present.
        if shutil.which("docker") is None:
            raise RuntimeError("docker binary not found; use local_process sandbox")
        # Create a container with the workspace mounted at /ws and no network.
        cmd = [
            "docker",
            "run",
            "-d",
            "--network",
            self.network,
            "-v",
            f"{self._ws}:/ws",
            self.image,
            "sleep",
            "infinity",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if proc.returncode != 0:
            raise RuntimeError(f"docker run failed: {proc.stderr.strip()}")
        self._container = proc.stdout.strip()
        return self._ws

    def destroy(self) -> None:
        if self._container:
            subprocess.run(["docker", "rm", "-f", self._container], capture_output=True, timeout=60)
            self._container = None
        if self._ws:
            shutil.rmtree(self._ws, ignore_errors=True)
            self._ws = None

    def workspace_path(self) -> str:
        if self._ws is None:
            raise RuntimeError("sandbox not prepared")
        return self._ws

    def run_command(self, command: str, *, timeout_s: float = 30.0) -> tuple[int, str]:
        if self._container is None:
            raise RuntimeError("sandbox not prepared")
        proc = subprocess.run(
            ["docker", "exec", self._container, "sh", "-c", command],
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
        return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def build_sandbox(kind: str, config: dict[str, Any]) -> Sandbox:
    """Build a sandbox from a task's ExecutionSpec (spec 12.1)."""
    if kind == "local_process":
        return LocalProcessSandbox(seed_workspace=config.get("seed_workspace"))
    if kind == "docker":
        return DockerSandbox(
            image=config.get("image", "python:3.12-slim"), network=config.get("network", "none")
        )
    raise ValueError(f"unsupported sandbox: {kind}")
