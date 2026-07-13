"""Persistence — sqlite store for runs, tasks, and traces.

A ``RunStore`` persists a completed run (goal, answer, cost, latency, task graph,
trace) so runs are auditable after the process exits. Uses stdlib ``sqlite3`` —
no extra dependency. The DB file defaults to ``polyagent.db`` in the CWD.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import UTC, datetime
from typing import Any

from polyagent.orchestration.types import RunResult

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    goal TEXT,
    answer TEXT,
    latency REAL,
    total_attempts INTEGER,
    cost_usd REAL,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS tasks (
    run_id TEXT,
    id TEXT,
    description TEXT,
    deps TEXT,
    status TEXT,
    result TEXT,
    attempts INTEGER,
    PRIMARY KEY (run_id, id)
);
CREATE TABLE IF NOT EXISTS traces (
    run_id TEXT PRIMARY KEY,
    span_json TEXT
);
"""


class RunStore:
    def __init__(self, path: str = "polyagent.db") -> None:
        self.path = path
        self._conn = sqlite3.connect(path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def save(self, *, goal: str, result: RunResult, trace: dict[str, Any]) -> str:
        run_id = uuid.uuid4().hex[:12]
        now = datetime.now(UTC).isoformat()
        self._conn.execute(
            "INSERT INTO runs VALUES (?,?,?,?,?,?,?)",
            (
                run_id,
                goal,
                result.answer,
                result.latency,
                result.total_attempts,
                result.estimated_cost_usd,
                now,
            ),
        )
        for task in result.task_graph:
            self._conn.execute(
                "INSERT INTO tasks VALUES (?,?,?,?,?,?,?)",
                (
                    run_id,
                    task.id,
                    task.description,
                    json.dumps(task.deps),
                    task.status.value,
                    task.result,
                    task.attempts,
                ),
            )
        self._conn.execute(
            "INSERT INTO traces VALUES (?,?)", (run_id, json.dumps(trace))
        )
        self._conn.commit()
        return run_id

    def list(self, limit: int = 20) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT id, goal, latency, total_attempts, cost_usd, created_at "
            "FROM runs ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get(self, run_id: str) -> dict[str, Any] | None:
        run = self._conn.execute(
            "SELECT * FROM runs WHERE id=?", (run_id,)
        ).fetchone()
        if run is None:
            return None
        tasks = self._conn.execute(
            "SELECT * FROM tasks WHERE run_id=?", (run_id,)
        ).fetchall()
        trace_row = self._conn.execute(
            "SELECT span_json FROM traces WHERE run_id=?", (run_id,)
        ).fetchone()
        return {
            "run": dict(run),
            "tasks": [dict(t) for t in tasks],
            "trace": json.loads(trace_row["span_json"]) if trace_row else None,
        }

    def close(self) -> None:
        self._conn.close()
