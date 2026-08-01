"""Persistent model-asset records (spec 2.2, Milestone 1).

Stores each registered asset as a portable JSON file under ``models/`` so
records survive GUI restarts, mirror the run-artifact convention, and are easy
to seed with synthetic fixtures. Queries are simple scans; counts are tiny.
"""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path

from eval_lab.schemas.model_asset import ModelAssetRecord

_ASSET_ID = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


class ModelAssetStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, asset_id: str) -> Path:
        if not _ASSET_ID.match(asset_id):
            raise ValueError(f"invalid asset id: {asset_id!r}")
        return self.root / f"{asset_id}.json"

    def new_id(self, prefix: str = "asset") -> str:
        return f"{prefix}-{uuid.uuid4().hex[:10]}"

    def save(self, record: ModelAssetRecord) -> ModelAssetRecord:
        path = self._path(record.asset_id)
        payload = record.model_dump(mode="json")
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(path)
        return record

    def get(self, asset_id: str) -> ModelAssetRecord | None:
        path = self._path(asset_id)
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return ModelAssetRecord.model_validate(data)
        except (OSError, json.JSONDecodeError, ValueError):
            return None

    def list(self) -> list[ModelAssetRecord]:
        out: list[ModelAssetRecord] = []
        for path in sorted(self.root.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                out.append(ModelAssetRecord.model_validate(data))
            except (OSError, json.JSONDecodeError, ValueError):
                continue
        return out

    def delete(self, asset_id: str) -> bool:
        path = self._path(asset_id)
        if not path.is_file():
            return False
        path.unlink()
        return True
