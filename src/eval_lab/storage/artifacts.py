"""Run workspace layout and artifact persistence (spec 16)."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path


class RunWorkspace:
    """Materializes the runs/<run-id>/ layout with manifest, result, traces."""

    def __init__(self, runs_root: str | Path, run_id: str) -> None:
        self.root = Path(runs_root) / run_id
        self.root.mkdir(parents=True, exist_ok=True)
        self.artifacts_dir = self.root / "artifacts"
        self.artifacts_dir.mkdir(exist_ok=True)
        self.validator_dir = self.root / "validator"
        self.validator_dir.mkdir(exist_ok=True)

    # -- paths --
    def manifest_path(self) -> Path:
        return self.root / "manifest.json"

    def result_path(self) -> Path:
        return self.root / "result.json"

    def trace_path(self) -> Path:
        return self.root / "trace.jsonl"

    def scores_path(self) -> Path:
        return self.root / "scores.jsonl"

    def report_path(self) -> Path:
        return self.root / "report.md"

    # -- writers --
    def write_manifest(self, manifest: dict[str, object]) -> None:
        self.manifest_path().write_text(
            json.dumps(manifest, indent=2, default=str), encoding="utf-8"
        )

    def write_result(self, result: dict[str, object]) -> None:
        self.result_path().write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")

    def append_scores(self, scores: list[dict[str, object]]) -> None:
        lines = [json.dumps(s, default=str) + "\n" for s in scores]
        with self.scores_path().open("a", encoding="utf-8") as fh:
            fh.writelines(lines)

    def store_artifact(self, name: str, data: bytes | str) -> str:
        """Write an artifact, return its relative path for the manifest."""
        rel = self.artifacts_dir / name
        raw = data.encode("utf-8") if isinstance(data, str) else data
        rel.write_bytes(raw)
        return str(rel.relative_to(self.root.parent.parent))


def sha256_of(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def fingerprint_dir(path: str | Path) -> str:
    """A deterministic content hash of a directory (sorted rel paths + hashes)."""
    base = Path(path)
    if not base.exists():
        return "MISSING"
    lines: list[str] = []
    for p in sorted(base.rglob("*")):
        if p.is_file():
            lines.append(f"{p.relative_to(base)}:{sha256_of(p)}")
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()


def copy_tree(src: str | Path, dst: str | Path) -> None:
    shutil.copytree(src, dst)
