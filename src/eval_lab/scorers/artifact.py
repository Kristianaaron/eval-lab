"""artifact scorer: verify an artifact exists and passes checks (spec 13.3)."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from eval_lab.schemas.models import ScoreResult
from eval_lab.scorers.base import register_scorer


class ArtifactScorer:
    """Check a produced artifact file against configured expectations.

    Config:
        path      artifact path relative to the workspace (run_dir, else cwd).
        hash      optional expected sha256 hex digest.
        min_size  optional minimum file size in bytes.

    A missing or mismatched artifact is a *legitimate* 0.0 (NOT an error).
    Setups that cannot resolve a valid workspace report ``error``.
    """

    scorer_id = "artifact"

    def __init__(self, path: str, hash: str | None = None, min_size: int | None = None) -> None:
        if not path:
            raise ValueError("artifact requires a non-empty path")
        self.path = path
        self.expected_hash = hash
        self.min_size = min_size

    def score(self, *, output: str, task: Any = None, run_dir: Any = None) -> ScoreResult:
        if run_dir is None and not Path.cwd().is_dir():
            return ScoreResult(
                scorer_id=self.scorer_id,
                score=0.0,
                passed=False,
                error="artifact scorer has no workspace to resolve the path against",
                details={"path": self.path},
            )
        base = Path(run_dir) if run_dir is not None else Path.cwd()
        target = base / self.path

        exists = target.is_file()
        size = target.stat().st_size if exists else None
        actual_hash = _sha256(target) if exists else None

        detail: dict[str, Any] = {
            "path": self.path,
            "exists": exists,
            "size": size,
            "hash": actual_hash,
            "expected_hash": self.expected_hash,
            "min_size": self.min_size,
        }
        failed: list[str] = []
        if not exists:
            failed.append("missing")
        if exists and self.min_size is not None and size is not None and size < self.min_size:
            failed.append(f"size {size} < min_size {self.min_size}")
        if exists and self.expected_hash and actual_hash != self.expected_hash:
            failed.append("hash_mismatch")
        detail["failures"] = failed
        passed = not failed
        return ScoreResult(
            scorer_id=self.scorer_id,
            score=1.0 if passed else 0.0,
            passed=passed,
            details=detail,
        )


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


register_scorer("artifact", ArtifactScorer)
