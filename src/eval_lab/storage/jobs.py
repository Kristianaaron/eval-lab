"""Persistent job store for the orchestrator (spec 14).

Each job is a portable JSON file under ``jobs/<kind>/<job_id>.json``, written
atomically so a crash mid-write never corrupts the record. Jobs survive GUI
restarts by construction.
"""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path

from eval_lab.schemas.job import Job

_JOB_ID = re.compile(r"^[a-z]+-[a-z0-9-]+$")


class JobStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, job_id: str) -> Path:
        if not _JOB_ID.match(job_id):
            raise ValueError(f"invalid job id: {job_id!r}")
        # job ids embed their kind prefix: <kind>-<suffix>.
        return self.root / f"{job_id}.json"

    def new_id(self, kind: str) -> str:
        return f"{kind}-{uuid.uuid4().hex[:10]}"

    def save(self, job: Job) -> Job:
        path = self._path(job.job_id)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(job.model_dump(mode="json"), indent=2), encoding="utf-8")
        tmp.replace(path)
        return job

    def get(self, job_id: str) -> Job | None:
        path = self._path(job_id)
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return Job.model_validate(data)
        except (OSError, json.JSONDecodeError, ValueError):
            return None

    def list(self, *, kind: str | None = None) -> list[Job]:
        out: list[Job] = []
        for path in sorted(self.root.glob("*.json")):
            job = self.get(path.stem)
            if job is not None and (kind is None or job.kind == kind):
                out.append(job)
        return out
