"""Append-only audit log (SQLite).

Every alert, diagnosis, policy decision, approval and action is recorded so there
is a complete, queryable trail and a basis for tuning policy over time.
"""

from __future__ import annotations

import json
import sqlite3
import time


class AuditStore:
    def __init__(self, path: str = "adr-audit.sqlite"):
        self.path = path
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS events (
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   ts REAL NOT NULL,
                   incident_id TEXT,
                   kind TEXT NOT NULL,
                   data TEXT NOT NULL
               )"""
        )
        self._conn.commit()

    def record(self, incident_id: str, kind: str, data: dict) -> None:
        self._conn.execute(
            "INSERT INTO events (ts, incident_id, kind, data) VALUES (?, ?, ?, ?)",
            (time.time(), incident_id, kind, json.dumps(data, default=str)),
        )
        self._conn.commit()

    def incident(self, incident_id: str) -> list[dict]:
        cur = self._conn.execute(
            "SELECT ts, kind, data FROM events WHERE incident_id = ? ORDER BY id",
            (incident_id,),
        )
        return [
            {"ts": ts, "kind": kind, "data": json.loads(data)} for ts, kind, data in cur.fetchall()
        ]

    def close(self) -> None:
        self._conn.close()


class NullAudit(AuditStore):
    """No-op audit store for tests."""

    def __init__(self):  # noqa: D107 - intentionally skips DB setup
        self._events: list[tuple] = []

    def record(self, incident_id, kind, data):
        self._events.append((incident_id, kind, data))

    def incident(self, incident_id):
        return [{"kind": k, "data": d} for i, k, d in self._events if i == incident_id]

    def close(self):
        pass
