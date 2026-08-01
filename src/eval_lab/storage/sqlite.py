"""SQLite-backed storage for run metadata (spec 16).

Stores indexed metadata for querying while JSON/JSONL remain the portable
source artifacts on disk (runs/<run-id>/...).
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path


class RunStore:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._migrate()

    def _migrate(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                task_id TEXT,
                task_version INTEGER,
                model_id TEXT,
                harness_id TEXT,
                suite_id TEXT,
                level TEXT,
                status TEXT,
                aggregate_score REAL,
                passed INTEGER,
                run_dir TEXT
            );
            CREATE TABLE IF NOT EXISTS scores (
                run_id TEXT NOT NULL,
                scorer_id TEXT NOT NULL,
                required INTEGER,
                passed INTEGER,
                score REAL,
                details TEXT,
                PRIMARY KEY (run_id, scorer_id)
            );
            CREATE TABLE IF NOT EXISTS meta (
                schema_version TEXT
            );
            """
        )
        self.conn.execute("INSERT OR IGNORE INTO meta (schema_version) VALUES ('1.0')")
        self.conn.commit()

    def insert_run(self, manifest: dict[str, object]) -> str:
        run_id_raw = manifest.get("run_id")
        run_id: str = run_id_raw if isinstance(run_id_raw, str) else uuid.uuid4().hex[:12]
        self.conn.execute(
            """INSERT OR REPLACE INTO runs
               (run_id, created_at, task_id, task_version, model_id, harness_id,
                suite_id, level, status, aggregate_score, passed, run_dir)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                run_id,
                manifest.get("created_at") or datetime.now(UTC).isoformat(),
                manifest.get("task_id"),
                manifest.get("task_version"),
                manifest.get("model_id"),
                manifest.get("harness_id"),
                manifest.get("suite_id"),
                manifest.get("level"),
                manifest.get("result_status", "pending"),
                manifest.get("aggregate_score"),
                1 if manifest.get("passed") else 0,
                manifest.get("run_dir"),
            ),
        )
        self.conn.commit()
        return run_id

    def insert_scores(self, run_id: str, scores: list[dict[str, object]]) -> None:
        for s in scores:
            self.conn.execute(
                """INSERT OR REPLACE INTO scores
                   (run_id, scorer_id, required, passed, score, details)
                   VALUES (?,?,?,?,?,?)""",
                (
                    run_id,
                    s.get("scorer_id"),
                    1 if s.get("required") else 0,
                    1 if s.get("passed") else 0,
                    s.get("score"),
                    json.dumps(s.get("details", {}), default=str),
                ),
            )
        self.conn.commit()

    def update_status(
        self,
        run_id: str,
        status: str,
        *,
        aggregate: float | None = None,
        passed: bool | None = None,
    ) -> None:
        self.conn.execute(
            "UPDATE runs SET status=? WHERE run_id=?",
            (status, run_id),
        )
        if aggregate is not None or passed is not None:
            self.conn.execute(
                "UPDATE runs SET aggregate_score=?, passed=? WHERE run_id=?",
                (aggregate, 1 if passed else 0, run_id),
            )
        self.conn.commit()

    def get_run(self, run_id: str) -> dict[str, object] | None:
        row = self.conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        return dict(row) if row else None

    def list_runs(self, *, limit: int = 100) -> list[dict[str, object]]:
        rows = self.conn.execute(
            "SELECT run_id, task_id, model_id, status, aggregate_score, "
            "passed, created_at FROM runs ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def run_scores(self, run_id: str) -> list[dict[str, object]]:
        rows = self.conn.execute(
            "SELECT scorer_id, required, passed, score, details "
            "FROM scores WHERE run_id=? ORDER BY rowid",
            (run_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def close(self) -> None:
        self.conn.close()
