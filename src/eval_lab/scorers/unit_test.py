"""unit_test scorer: run a shell command and reward exit 0 (spec 13.3)."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Any

from eval_lab.schemas.models import ScoreResult
from eval_lab.scorers.base import register_scorer

_STD_HEAD = 2000


class UnitTestScorer:
    """Run ``command`` in a workspace; pass iff the process exits 0.

    Config:
        command          the shell command to run (required).
        workspace        working directory (default: run_dir, else cwd).
        timeout_seconds  subprocess timeout (default 60).

    A failure to *launch* the process is a setup failure and reports ``error``
    (never a silent zero, never a raised exception). A non-zero exit is a
    legitimate 0.0 failure.
    """

    scorer_id = "unit_test"

    def __init__(
        self, command: str, workspace: str | None = None, timeout_seconds: int = 60
    ) -> None:
        if not command or not command.strip():
            raise ValueError("unit_test requires a non-empty command")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.command = command
        self.workspace = workspace
        self.timeout_seconds = timeout_seconds

    def score(self, *, output: str, task: Any = None, run_dir: Any = None) -> ScoreResult:
        base: str
        if self.workspace:
            base = self.workspace
        elif run_dir is not None:
            base = str(run_dir)
        else:
            base = str(Path.cwd())

        start = time.monotonic()
        try:
            proc = subprocess.run(
                self.command,
                shell=True,
                cwd=base,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
            )
            duration_s = round(time.monotonic() - start, 3)
        except subprocess.TimeoutExpired as exc:
            return ScoreResult(
                scorer_id=self.scorer_id,
                score=0.0,
                passed=False,
                details={
                    "command": self.command,
                    "workspace": base,
                    "exit_code": None,
                    "timed_out": True,
                    "duration_s": float(self.timeout_seconds),
                    "stdout_head": _maybe_head(exc.stdout),
                    "stderr_head": _maybe_head(exc.stderr),
                },
            )
        except OSError as exc:
            # Setup failure: process could not be launched -> error.
            return ScoreResult(
                scorer_id=self.scorer_id,
                score=0.0,
                passed=False,
                error=f"failed to run command in {base!r}: {exc}",
                details={"command": self.command, "workspace": base},
            )

        passed = proc.returncode == 0
        return ScoreResult(
            scorer_id=self.scorer_id,
            score=1.0 if passed else 0.0,
            passed=passed,
            details={
                "command": self.command,
                "workspace": base,
                "exit_code": proc.returncode,
                "duration_s": duration_s,
                "stdout_head": proc.stdout[:_STD_HEAD],
                "stderr_head": proc.stderr[:_STD_HEAD],
            },
        )


def _maybe_head(text: object) -> str:
    if not isinstance(text, str):
        return ""
    return text[:_STD_HEAD]


register_scorer("unit_test", UnitTestScorer)
