"""Persistent atlas-bridge import records (eval-lab consumer).

Mirrors ``storage/model_assets.py``: each imported run is a portable JSON file
so records survive GUI restarts. The bridge persists to
``<out_root>/atlas_runs/<id>/import.json``, so the store keys its files by run
dir under its root (one ``<run_id>/import.json`` per run).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from eval_lab.schemas.atlas_bridge import AtlasBridgeImport

_RUN_ID = re.compile(r"^[a-zA-Z0-9._-]+$")


class AtlasImportStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, run_id: str) -> Path:
        if not _RUN_ID.match(run_id):
            raise ValueError(f"invalid run id: {run_id!r}")
        return self.root / run_id / "import.json"

    def save(self, record: AtlasBridgeImport) -> AtlasBridgeImport:
        path = self._path(record.run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = record.model_dump(mode="json")
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(path)
        return record

    def get(self, run_id: str) -> AtlasBridgeImport | None:
        path = self._path(run_id)
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return AtlasBridgeImport.model_validate(data)
        except (OSError, json.JSONDecodeError, ValueError):
            return None

    def delete(self, run_id: str) -> bool:
        path = self._path(run_id)
        if not path.is_file():
            return False
        path.unlink()
        return True
