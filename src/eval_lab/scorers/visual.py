"""visual scorer: deterministic scene/geometry or image similarity checks (spec 13.3)."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

from eval_lab.schemas.models import ScoreResult
from eval_lab.scorers.base import register_scorer


class VisualScorer:
    """Score a rendered scene or produced image.

    Mode ``json_scene`` loads a scene JSON (default ``artifacts/scene.json`` in
    run_dir) and runs deterministic geometry checks against ``expected``:
    ``object_counts``, ``required_keys``, ``bounds``, ``collision``, ``volume``.

    Mode ``image`` compares a produced file against a reference using ``exact``
    sha256 equality or a normalized byte-``diff`` (deterministic).

    A reference/produced target that is missing yields ``error`` (cannot score)
    unless ``required: false``, in which case it is a legitimate 0.0.
    """

    scorer_id = "visual"

    def __init__(
        self,
        mode: str,
        *,
        path: str | None = None,
        expected: dict[str, Any] | None = None,
        produced: str | None = None,
        reference: str | None = None,
        reference_dir: str | None = None,
        method: str = "exact",
        tolerance: float = 0.0,
        pass_threshold: float = 1.0,
        required: bool = True,
    ) -> None:
        if mode not in ("json_scene", "image"):
            raise ValueError(f"visual: unsupported mode {mode!r}")
        self.mode = mode
        self.path = path
        self.expected = expected or {}
        self.produced = produced
        self.reference = reference
        self.reference_dir = reference_dir
        self.method = method
        self.tolerance = tolerance
        self.pass_threshold = pass_threshold
        self.required = required

    def score(self, *, output: str, task: Any = None, run_dir: Any = None) -> ScoreResult:
        if self.mode == "json_scene":
            return self._score_scene(run_dir)
        return self._score_image(run_dir)

    # -- json_scene ---------------------------------------------------------
    def _score_scene(self, run_dir: Any) -> ScoreResult:
        base = run_dir if run_dir is not None else Path.cwd()
        rel = self.path or "artifacts/scene.json"
        scene_path = Path(base) / rel
        if not scene_path.is_file():
            if not self.required:
                return self._binary_failure(f"scene not found: {scene_path}", "missing")
            return ScoreResult(
                scorer_id=self.scorer_id,
                score=0.0,
                passed=False,
                error=f"scene not found: {scene_path}",
                details={"path": str(scene_path), "mode": self.mode, "required": True},
            )
        try:
            data = json.loads(scene_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            if not self.required:
                return self._binary_failure(f"invalid scene JSON: {exc}", "invalid")
            return ScoreResult(
                scorer_id=self.scorer_id,
                score=0.0,
                passed=False,
                error=f"invalid scene JSON: {exc}",
                details={"path": str(scene_path)},
            )

        objects = _scene_objects(data)
        checks: list[dict[str, Any]] = []
        expected = self.expected

        if "object_counts" in expected:
            checks.append(self._check_counts(objects, expected["object_counts"]))
        if "required_keys" in expected:
            keys = expected["required_keys"]
            checks.append(self._check_keys(objects, keys))
        if "bounds" in expected:
            checks.append(self._check_bounds(objects, expected["bounds"]))
        if "collision" in expected:
            min_sep = float(expected["collision"].get("min_separation", 0.0))
            checks.append(self._check_collision(objects, min_sep))
        if "volume" in expected:
            checks.append(self._check_volume(objects, expected["volume"]))

        if not checks:
            return ScoreResult(
                scorer_id=self.scorer_id,
                score=0.0,
                passed=False,
                error="visual(json_scene): expected config has no checks",
                details={"path": str(scene_path)},
            )

        passed_checks = sum(1 for c in checks if c["passed"])
        score = passed_checks / len(checks)
        passed = score + 1e-9 >= self.pass_threshold
        return ScoreResult(
            scorer_id=self.scorer_id,
            score=round(score, 4),
            passed=passed,
            details={
                "mode": self.mode,
                "path": str(scene_path),
                "object_count": len(objects),
                "checks": checks,
                "passed_checks": passed_checks,
                "total_checks": len(checks),
                "pass_threshold": self.pass_threshold,
            },
        )

    def _check_counts(
        self, objects: list[dict[str, Any]], expected: dict[str, Any]
    ) -> dict[str, Any]:
        actual: dict[str, int] = {}
        for obj in objects:
            t = str(obj.get("type", "unknown"))
            actual[t] = actual.get(t, 0) + 1
        mismatches = {
            t: {"expected": int(n), "actual": actual.get(t, 0)}
            for t, n in expected.items()
            if int(n) != actual.get(t, 0)
        }
        return {
            "name": "object_counts",
            "passed": not mismatches,
            "actual": actual,
            "expected": expected,
            "mismatches": mismatches,
        }

    def _check_keys(self, objects: list[dict[str, Any]], keys: list[str]) -> dict[str, Any]:
        missing: dict[int, list[str]] = {}
        for i, obj in enumerate(objects):
            miss = [k for k in keys if k not in obj]
            if miss:
                missing[i] = miss
        strmissing = {str(k): v for k, v in missing.items()}
        return {
            "name": "required_keys",
            "passed": not missing,
            "missing": strmissing,
            "keys": list(keys),
        }

    def _check_bounds(
        self, objects: list[dict[str, Any]], bounds: dict[str, Any]
    ) -> dict[str, Any]:
        violations: list[dict[str, Any]] = []
        for i, obj in enumerate(objects):
            c = _coords(obj)
            if c is None:
                violations.append({"object": i, "reason": "no coordinates"})
                continue
            for axis, (lo, hi) in bounds.items():
                v = c.get(axis)
                if v is None:
                    violations.append({"object": i, "axis": axis, "reason": "missing coordinate"})
                elif not (float(lo) <= float(v) <= float(hi)):
                    violations.append({"object": i, "axis": axis, "value": v, "bounds": [lo, hi]})
        return {
            "name": "bounds",
            "passed": not violations,
            "violations": violations,
            "bounds": dict(bounds),
        }

    def _check_collision(self, objects: list[dict[str, Any]], min_sep: float) -> dict[str, Any]:
        collisions: list[dict[str, Any]] = []
        centers = [_coords(o) for o in objects]
        for i in range(len(objects)):
            for j in range(i + 1, len(objects)):
                ci = centers[i]
                cj = centers[j]
                if ci is None or cj is None:
                    collisions.append({"pair": [i, j], "reason": "missing coordinates"})
                    continue
                d = _dist(ci, cj)
                if d < min_sep:
                    collisions.append(
                        {"pair": [i, j], "distance": round(d, 4), "min_separation": min_sep}
                    )
        return {
            "name": "collision",
            "passed": not collisions,
            "collisions": collisions,
            "min_separation": min_sep,
        }

    def _check_volume(
        self, objects: list[dict[str, Any]], expected: dict[str, Any]
    ) -> dict[str, Any]:
        failures: list[dict[str, Any]] = []
        lo = expected.get("min")
        hi = expected.get("max")
        for i, obj in enumerate(objects):
            v = _volume(obj)
            if v is None:
                failures.append({"object": i, "reason": "cannot compute volume"})
                continue
            if lo is not None and v < float(lo):
                failures.append({"object": i, "volume": round(v, 4), "min": lo})
            if hi is not None and v > float(hi):
                failures.append({"object": i, "volume": round(v, 4), "max": hi})
        return {
            "name": "volume",
            "passed": not failures,
            "failures": failures,
            "expected": expected,
        }

    # -- image --------------------------------------------------------------
    def _score_image(self, run_dir: Any) -> ScoreResult:
        base = run_dir if run_dir is not None else Path.cwd()
        produced_path = Path(base) / (self.produced or "") if self.produced is not None else None
        if produced_path is None or not produced_path.is_file():
            produced_str = str(produced_path) if produced_path is not None else self.produced
            return self._missing_image(
                base, produced_path, "none", "produced image missing", produced=produced_str
            )
        ref_path = self._resolve_reference(base, produced_path)
        if ref_path is None or not ref_path.is_file():
            ref_str = str(ref_path) if ref_path is not None else self.reference
            return self._missing_image(
                base,
                produced_path,
                "reference",
                "reference image missing",
                reference=ref_str,
                produced=str(produced_path),
            )
        try:
            pbytes = produced_path.read_bytes()
            rbytes = ref_path.read_bytes()
        except OSError as exc:
            return ScoreResult(
                scorer_id=self.scorer_id,
                score=0.0,
                passed=False,
                error=f"cannot read produced/reference: {exc}",
                details={"produced": str(produced_path), "reference": str(ref_path)},
            )

        if self.method == "exact":
            match = _sha256_bytes(pbytes) == _sha256_bytes(rbytes)
            score = 1.0 if match else 0.0
        elif self.method == "diff":
            score = _byte_diff_score(pbytes, rbytes)
        else:
            return ScoreResult(
                scorer_id=self.scorer_id,
                score=0.0,
                passed=False,
                error=f"visual(image): unknown method {self.method!r}",
                details={},
            )
        passed = score + 1e-9 >= 1.0 - self.tolerance
        return ScoreResult(
            scorer_id=self.scorer_id,
            score=round(score, 4),
            passed=passed,
            details={
                "mode": self.mode,
                "method": self.method,
                "produced": str(produced_path),
                "reference": str(ref_path),
                "score": round(score, 4),
                "tolerance": self.tolerance,
                "pass_threshold": 1.0 - self.tolerance,
            },
        )

    def _resolve_reference(self, base: Path, produced_path: Path) -> Path | None:
        if self.reference:
            return Path(base) / self.reference
        if self.reference_dir:
            return Path(self.reference_dir) / produced_path.name
        if self.produced:
            return Path(base) / f"{self.produced}.expected"
        return None

    def _missing_image(
        self, base: Path, produced_path: Path | None, kind: str, reason: str, **extra: Any
    ) -> ScoreResult:
        detail: dict[str, Any] = {"mode": self.mode, "reason": reason, **extra}
        if not self.required:
            detail["required"] = False
            return ScoreResult(
                scorer_id=self.scorer_id,
                score=0.0,
                passed=False,
                details=detail,
            )
        detail["required"] = True
        return ScoreResult(
            scorer_id=self.scorer_id,
            score=0.0,
            passed=False,
            error=reason,
            details=detail,
        )

    def _binary_failure(self, reason: str, code: str) -> ScoreResult:
        return ScoreResult(
            scorer_id=self.scorer_id,
            score=0.0,
            passed=False,
            details={"mode": self.mode, "reason": reason, "code": code, "required": False},
        )


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------


def _scene_objects(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [o for o in data if isinstance(o, dict)]
    if isinstance(data, dict):
        objs = data.get("objects")
        if isinstance(objs, list):
            return [o for o in objs if isinstance(o, dict)]
        if "type" in data or "x" in data:
            return [data]
    return []


def _coords(obj: dict[str, Any]) -> dict[str, float] | None:
    if all(k in obj for k in ("x", "y", "z")):
        return {"x": float(obj["x"]), "y": float(obj["y"]), "z": float(obj["z"])}
    return None


def _dist(a: dict[str, float], b: dict[str, float]) -> float:
    return math.sqrt(sum((a[k] - b[k]) ** 2 for k in ("x", "y", "z")))


def _volume(obj: dict[str, Any]) -> float | None:
    t = str(obj.get("type", ""))
    if "length" in obj and "width" in obj and "height" in obj:
        return float(obj["length"]) * float(obj["width"]) * float(obj["height"])
    if t == "sphere" and "radius" in obj:
        return (4.0 / 3.0) * math.pi * float(obj["radius"]) ** 3
    if "volume" in obj:
        return float(obj["volume"])
    return None


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _byte_diff_score(a: bytes, b: bytes) -> float:
    n = max(len(a), len(b), 1)
    diffs = sum(1 for i in range(min(len(a), len(b))) if a[i] != b[i])
    diffs += abs(len(a) - len(b))
    return max(0.0, 1.0 - diffs / n)


register_scorer("visual", VisualScorer)
