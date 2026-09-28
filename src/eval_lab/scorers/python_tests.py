"""python_tests scorer: hidden unittest suite with per-test partial credit (spec 13.3).

Where ``unit_test`` rewards only "the command exited 0", this scorer runs a
*hidden* stdlib ``unittest`` suite shipped with the task and reports the
fraction of individual tests that passed. Deep coding tasks ship 10–40 tests
covering edge cases, error contracts and performance guards, so a model that
gets the happy path right but misses an invariant is scored 0.7, not 0.

Two modes:

- ``extract`` (direct tasks): the model's reply is parsed for a fenced code
  block which is written to ``solution_file`` inside a fresh temp workspace
  next to the copied tests.
- ``workspace`` (agent tasks): the tests are copied into the sandbox workspace
  the agent worked in (``run_dir``) and run against the files it left behind.
  The agent never sees them because they live in the task package, not the
  workspace fixture.

Only the Python interpreter running eval-lab is required; no pytest.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from eval_lab.schemas.models import ScoreResult
from eval_lab.scorers.base import register_scorer

_RUNNER = r"""
import json, sys, unittest, io, os, traceback
tests_dir, top = sys.argv[1], sys.argv[2]
class _Result(unittest.TestResult):
    def __init__(self):
        super().__init__(); self.rows = []
    def _row(self, test, status, err=None):
        detail = "".join(traceback.format_exception(*err))[-800:] if err else ""
        self.rows.append({"id": test.id(), "status": status, "detail": detail})
    def addSuccess(self, test):
        super().addSuccess(test); self._row(test, "pass")
    def addFailure(self, test, err):
        super().addFailure(test, err); self._row(test, "fail", err)
    def addError(self, test, err):
        super().addError(test, err); self._row(test, "error", err)
    def addSkip(self, test, reason):
        super().addSkip(test, reason); self.rows.append({"id": test.id(), "status": "skip", "detail": reason})
    def addExpectedFailure(self, test, err):
        super().addExpectedFailure(test, err); self._row(test, "pass")
    def addUnexpectedSuccess(self, test):
        super().addUnexpectedSuccess(test); self._row(test, "fail")
sys.path.insert(0, top)
loader = unittest.TestLoader()
try:
    suite = loader.discover(tests_dir, pattern="test*.py", top_level_dir=top)
except Exception:
    print(json.dumps({"rows": [], "load_error": traceback.format_exc()[-1500:]})); sys.exit(0)
res = _Result()
sys.stdout, real = io.StringIO(), sys.stdout
try:
    suite.run(res)
finally:
    sys.stdout = real
load_errors = [r for r in res.rows if r["id"].startswith("unittest.loader")]
print(json.dumps({"rows": res.rows, "load_error": load_errors[0]["detail"] if load_errors else None}))
"""

_FENCE = re.compile(r"```(?:python|py|python3)?\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)


def extract_python(text: str, strategy: str = "largest") -> str:
    """Pull the solution code out of a model reply."""
    blocks = [b for b in _FENCE.findall(text or "") if b.strip()]
    if not blocks:
        return text or ""
    if strategy == "last":
        return blocks[-1]
    if strategy == "first":
        return blocks[0]
    if strategy == "concat":
        return "\n\n".join(blocks)
    return max(blocks, key=len)


class PythonTestsScorer:
    scorer_id = "python_tests"

    def __init__(
        self,
        tests: str = "tests",
        solution_file: str = "solution.py",
        mode: str = "extract",
        extract: str = "largest",
        support_files: list[str] | None = None,
        min_pass_fraction: float = 1.0,
        timeout_seconds: int = 120,
    ) -> None:
        if mode not in ("extract", "workspace"):
            raise ValueError("mode must be 'extract' or 'workspace'")
        if not 0.0 <= min_pass_fraction <= 1.0:
            raise ValueError("min_pass_fraction must be within [0, 1]")
        self.tests = tests
        self.solution_file = solution_file
        self.mode = mode
        self.extract = extract
        self.support_files = list(support_files or [])
        self.min_pass_fraction = min_pass_fraction
        self.timeout_seconds = timeout_seconds

    # -- helpers ------------------------------------------------------------
    def _tests_src(self, task: Any) -> Path | None:
        base = getattr(task, "source_dir", None)
        candidate = Path(base) / self.tests if base else Path(self.tests)
        return candidate if candidate.is_dir() else None

    def _prepare_workspace(self, output: str, task: Any, run_dir: Any) -> tuple[Path, bool]:
        """Return (workspace, is_temporary)."""
        tests_src = self._tests_src(task)
        if tests_src is None:
            raise FileNotFoundError(f"hidden tests directory not found: {self.tests}")
        if self.mode == "workspace":
            if run_dir is None:
                raise FileNotFoundError("workspace mode needs the agent workspace (run_dir)")
            ws = Path(run_dir)
            hidden = ws / "_hidden_tests"
            if hidden.exists():
                shutil.rmtree(hidden)
            shutil.copytree(tests_src, hidden)
            _ensure_package(hidden)
            return ws, False
        ws = Path(tempfile.mkdtemp(prefix="eval-lab-pytests-"))
        shutil.copytree(tests_src, ws / "_hidden_tests")
        _ensure_package(ws / "_hidden_tests")
        base = Path(task.source_dir) if getattr(task, "source_dir", None) else Path.cwd()
        for rel in self.support_files:
            src = base / rel
            if src.is_file():
                dst = ws / Path(rel).name
                shutil.copy2(src, dst)
            elif src.is_dir():
                shutil.copytree(src, ws / Path(rel).name, dirs_exist_ok=True)
        code = extract_python(output, self.extract)
        (ws / self.solution_file).write_text(code, encoding="utf-8")
        return ws, True

    # -- scoring ------------------------------------------------------------
    def score(self, *, output: str, task: Any = None, run_dir: Any = None) -> ScoreResult:
        try:
            ws, temporary = self._prepare_workspace(output, task, run_dir)
        except (FileNotFoundError, OSError) as exc:
            return ScoreResult(
                scorer_id=self.scorer_id, error=str(exc), details={"tests": self.tests}
            )

        runner = ws / "_run_hidden_tests.py"
        runner.write_text(_RUNNER, encoding="utf-8")
        start = time.monotonic()
        try:
            proc = subprocess.run(
                [sys.executable, "-I", str(runner), str(ws / "_hidden_tests"), str(ws)],
                cwd=ws,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                env={"PYTHONHASHSEED": "0", "PATH": "/usr/bin:/bin"},
            )
        except subprocess.TimeoutExpired:
            return self._finish(
                ws, temporary, rows=[], timed_out=True, duration=float(self.timeout_seconds)
            )
        except OSError as exc:
            if temporary:
                shutil.rmtree(ws, ignore_errors=True)
            return ScoreResult(scorer_id=self.scorer_id, error=f"failed to launch tests: {exc}")
        duration = time.monotonic() - start

        rows: list[dict[str, Any]] = []
        load_error: str | None = None
        last = (proc.stdout or "").strip().splitlines()
        if last:
            try:
                payload = json.loads(last[-1])
                rows = list(payload.get("rows") or [])
                load_error = payload.get("load_error")
            except json.JSONDecodeError:
                load_error = (proc.stdout or "")[-800:] + (proc.stderr or "")[-800:]
        else:
            load_error = (proc.stderr or "")[-1200:] or "test runner produced no output"
        return self._finish(ws, temporary, rows=rows, load_error=load_error, duration=duration)

    def _finish(
        self,
        ws: Path,
        temporary: bool,
        *,
        rows: list[dict[str, Any]],
        load_error: str | None = None,
        timed_out: bool = False,
        duration: float = 0.0,
    ) -> ScoreResult:
        if temporary:
            shutil.rmtree(ws, ignore_errors=True)
        # ``unittest.loader._FailedTest`` rows mean the module could not be
        # imported (syntax error / missing symbol); they are not real tests.
        loader_failures = [r for r in rows if str(r.get("id", "")).startswith("unittest.loader")]
        if loader_failures and not load_error:
            load_error = loader_failures[0].get("detail")
        counted = [
            r
            for r in rows
            if r.get("status") != "skip" and not str(r.get("id", "")).startswith("unittest.loader")
        ]
        passed_n = sum(1 for r in counted if r.get("status") == "pass")
        total = len(counted)
        fraction = passed_n / total if total else 0.0
        details: dict[str, Any] = {
            "tests_total": total,
            "tests_passed": passed_n,
            "pass_fraction": fraction,
            "min_pass_fraction": self.min_pass_fraction,
            "timed_out": timed_out,
            "duration_s": round(duration, 3),
            "failed": [
                {"id": r["id"], "status": r["status"], "detail": (r.get("detail") or "")[:400]}
                for r in counted
                if r.get("status") != "pass"
            ][:25],
        }
        if load_error:
            details["load_error"] = load_error[:1200]
        if total == 0 and not timed_out:
            # The suite could not even be imported (syntax error in the solution,
            # missing symbol…): a legitimate zero, with the reason attached.
            details["reason"] = "no tests ran"
        return ScoreResult(
            scorer_id=self.scorer_id,
            score=fraction,
            passed=total > 0 and fraction >= self.min_pass_fraction and not timed_out,
            details=details,
        )


def _ensure_package(path: Path) -> None:
    """unittest discovery with a top-level dir needs the tests dir importable."""
    init = path / "__init__.py"
    if not init.exists():
        init.write_text("", encoding="utf-8")


register_scorer("python_tests", PythonTestsScorer)
