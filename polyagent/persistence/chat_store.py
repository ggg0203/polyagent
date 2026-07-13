"""ChatStore — SQLite-backed cross-session chat memory.

Persists shell/talk conversation history so the next session can pick up
where the user left off. Uses stdlib ``sqlite3`` — no extra dependency.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import UTC, datetime
from typing import Any

from polyagent.core.types import Message, Role, ToolCall

_DB_DIR = os.path.expanduser("~/.polyagent")
_DB_PATH = os.path.join(_DB_DIR, "chat_history.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS chat_sessions (
    id TEXT PRIMARY KEY,
    mode TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES chat_sessions(id),
    role TEXT NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    tool_calls_json TEXT,
    tool_call_id TEXT,
    created_at TEXT NOT NULL,
    msg_order INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_messages_session
    ON chat_messages(session_id, msg_order);
"""


class ChatStore:
    """Simple SQLite-backed chat history store.

    Parameters
    ----------
    db_path : str, optional
        Path to the SQLite database file. Defaults to ``~/.polyagent/chat_history.db``.
    """

    def __init__(self, db_path: str | None = None) -> None:
        path = db_path or _DB_PATH
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self._conn = sqlite3.connect(path)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    # ── public helpers ──────────────────────────────────────────────────── #

    def save_messages(self, messages: list[Message], mode: str, max_load: int = 40) -> None:
        """Save a list of messages to the current (or new) session.

        Keeps at most ``max_load`` USER + ASSISTANT + TOOL messages in the
        session (drops oldest ones when the count exceeds the limit).
        System messages are never counted.
        """
        now = _now()
        session_id = self._ensure_session(mode)

        # Determine next msg_order
        cur = self._conn.execute(
            "SELECT COALESCE(MAX(msg_order), 0) FROM chat_messages WHERE session_id = ?",
            (session_id,),
        )
        next_order = (cur.fetchone() or (0,))[0] + 1

        for msg in messages:
            if msg.role == Role.SYSTEM:
                continue
            tool_calls_json = _tool_calls_to_json(msg.tool_calls) if msg.tool_calls else None
            self._conn.execute(
                """INSERT INTO chat_messages
                   (session_id, role, content, tool_calls_json, tool_call_id,
                    created_at, msg_order)
                   VALUES (?,?,?,?,?,?,?)""",
                (
                    session_id,
                    msg.role.value,
                    msg.content or "",
                    tool_calls_json,
                    msg.tool_call_id,
                    now,
                    next_order,
                ),
            )
            next_order += 1

        self._conn.execute(
            "UPDATE chat_sessions SET updated_at = ? WHERE id = ?",
            (now, session_id),
        )
        self._conn.commit()

        # Prune old messages beyond limit
        self._prune_old(session_id, max_load)

    def load_last_session(self, mode: str, max_messages: int = 20) -> list[Message]:
        """Load the most recent session's latest messages as a Message list.

        Returns messages in chronological order, ready to be appended to the
        current conversation (``Message(role=SYSTEM, ...)`` is excluded).
        """
        # Find the most recent session for this mode
        cur = self._conn.execute(
            "SELECT id FROM chat_sessions WHERE mode = ? ORDER BY updated_at DESC LIMIT 1",
            (mode,),
        )
        row = cur.fetchone()
        if not row:
            return []
        session_id = row[0]

        # Fetch last N messages in chronological order
        cur = self._conn.execute(
            """SELECT role, content, tool_calls_json, tool_call_id
               FROM chat_messages
               WHERE session_id = ?
               ORDER BY msg_order ASC""",
            (session_id,),
        )
        rows = cur.fetchall()
        if not rows:
            return []

        # Take only the last max_messages
        rows = rows[-max_messages:]

        msgs: list[Message] = []
        for role, content, tc_json, tc_id in rows:
            tool_calls = _json_to_tool_calls(tc_json) if tc_json else None
            msgs.append(
                Message(
                    role=Role(role),
                    content=content or "",
                    tool_calls=tool_calls,
                    tool_call_id=tc_id,
                )
            )
        return msgs

    def close(self) -> None:
        self._conn.close()

    # ── internal ─────────────────────────────────────────────────────────── #

    def _ensure_session(self, mode: str) -> str:
        """Get or create a session for today."""
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        # Reuse today's existing session if any
        cur = self._conn.execute(
            "SELECT id FROM chat_sessions WHERE mode = ? AND date(created_at) = ? ORDER BY created_at DESC LIMIT 1",
            (mode, today),
        )
        row = cur.fetchone()
        if row:
            return str(row[0])
        sid = _new_id()
        now = _now()
        self._conn.execute(
            "INSERT INTO chat_sessions (id, mode, created_at, updated_at) VALUES (?,?,?,?)",
            (sid, mode, now, now),
        )
        self._conn.commit()
        return sid

    def _prune_old(self, session_id: str, keep: int) -> None:
        """Remove old messages beyond the ``keep`` limit (only count non-system)."""
        cur = self._conn.execute(
            "SELECT COUNT(*) FROM chat_messages WHERE session_id = ? AND role != 'system'",
            (session_id,),
        )
        total = (cur.fetchone() or (0,))[0]
        if total <= keep:
            return
        excess = total - keep
        # Delete the oldest excess messages
        self._conn.execute(
            """DELETE FROM chat_messages WHERE id IN (
                SELECT id FROM chat_messages
                WHERE session_id = ? AND role != 'system'
                ORDER BY msg_order ASC LIMIT ?
            )""",
            (session_id, excess),
        )
        self._conn.commit()


# ── helpers ──────────────────────────────────────────────────────────────── #


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S")


def _new_id() -> str:
    import uuid

    return uuid.uuid4().hex[:12]


def _tool_calls_to_json(calls: list[ToolCall]) -> str:
    return json.dumps(
        [{"id": c.id, "name": c.name, "arguments": c.arguments} for c in calls],
        ensure_ascii=False,
    )


def _json_to_tool_calls(raw: str) -> list[ToolCall]:
    data: list[dict[str, Any]] = json.loads(raw)
    return [
        ToolCall(id=item["id"], name=item["name"], arguments=item.get("arguments", "{}"))
        for item in data
    ]
