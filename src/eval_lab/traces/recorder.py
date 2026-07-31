"""Append-only trace recorder (spec 6.5)."""

from __future__ import annotations

import json
import time
from pathlib import Path


class TraceRecorder:
    """Write append-only JSON lines with monotonic sequence numbers."""

    def __init__(self, run_id: str, path: str | Path) -> None:
        self.run_id = run_id
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = self.path.open("a", encoding="utf-8")
        self._seq = 0

    def record(
        self,
        event_type: str,
        payload: dict[str, object],
        *,
        span_id: str | None = None,
        parent_span_id: str | None = None,
    ) -> None:
        event = {
            "schema_version": "1.0",
            "run_id": self.run_id,
            "sequence": self._seq,
            "time_monotonic_ns": time.monotonic_ns(),
            "event_type": event_type,
            "span_id": span_id,
            "parent_span_id": parent_span_id,
            "payload": payload,
        }
        self._seq += 1
        self._fh.write(json.dumps(event) + "\n")
        self._fh.flush()

    def close(self) -> None:
        self._fh.close()
