"""Persistent experiment records (Milestone 5).

Stores each experiment as a portable JSON file under ``experiments/`` mirroring
the model-asset store: survives restarts, easy to scan, trivial counts.
"""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path

from eval_lab.schemas.experiment import ExperimentRecord

_EXPERIMENT_ID = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


class ExperimentStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, experiment_id: str) -> Path:
        if not _EXPERIMENT_ID.match(experiment_id):
            raise ValueError(f"invalid experiment id: {experiment_id!r}")
        return self.root / f"{experiment_id}.json"

    def new_id(self, prefix: str = "experiment") -> str:
        return f"{prefix}-{uuid.uuid4().hex[:10]}"

    def save(self, record: ExperimentRecord) -> ExperimentRecord:
        path = self._path(record.experiment_id)
        payload = record.model_dump(mode="json")
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(path)
        return record

    def get(self, experiment_id: str) -> ExperimentRecord | None:
        path = self._path(experiment_id)
        if not path.is_file():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        return ExperimentRecord.model_validate(payload)

    def list(self) -> list[ExperimentRecord]:
        out: list[ExperimentRecord] = []
        for p in sorted(self.root.glob("*.json")):
            try:
                payload = json.loads(p.read_text(encoding="utf-8"))
                out.append(ExperimentRecord.model_validate(payload))
            except Exception:
                continue
        return out

    def delete(self, experiment_id: str) -> bool:
        path = self._path(experiment_id)
        if path.is_file():
            path.unlink()
            return True
        return False
