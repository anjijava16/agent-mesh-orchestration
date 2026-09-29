"""Durable state, in SQLite.

Three things live here, and each one exists because the deck makes a claim
about it:

  a2a_tasks     a task must outlive the process that accepted it, so `GetTask`
                still answers after a restart during a four-hour approval wait
  checkpoints   the orchestrator graph is saved after every node
  audit         every tool call, task transition and decision, with a trace id

SQLite keeps the project runnable with nothing installed. Swap this module for
Postgres and nothing above it changes.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from refundry.config import settings

_lock = threading.RLock()
_conn: sqlite3.Connection | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS a2a_tasks (
    id          TEXT PRIMARY KEY,
    context_id  TEXT NOT NULL,
    agent       TEXT NOT NULL,
    state       TEXT NOT NULL,
    payload     TEXT NOT NULL,
    created_at  REAL NOT NULL,
    updated_at  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_tasks_ctx ON a2a_tasks(context_id);

CREATE TABLE IF NOT EXISTS checkpoints (
    thread_id   TEXT PRIMARY KEY,
    node        TEXT NOT NULL,
    state       TEXT NOT NULL,
    updated_at  REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS cases (
    case_id     TEXT PRIMARY KEY,
    context_id  TEXT NOT NULL,
    status      TEXT NOT NULL,
    record      TEXT NOT NULL,
    updated_at  REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS case_notes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id     TEXT NOT NULL,
    author      TEXT NOT NULL,
    note        TEXT NOT NULL,
    at          REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS refund_ledger (
    idempotency_key TEXT PRIMARY KEY,
    case_id     TEXT NOT NULL,
    refund_ref  TEXT NOT NULL,
    amount      REAL NOT NULL,
    tender      TEXT NOT NULL,
    approver    TEXT,
    at          REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS audit (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    at          REAL NOT NULL,
    trace_id    TEXT,
    context_id  TEXT,
    actor       TEXT NOT NULL,
    kind        TEXT NOT NULL,
    target      TEXT,
    detail      TEXT
);
CREATE INDEX IF NOT EXISTS ix_audit_ctx ON audit(context_id);
"""


def connect() -> sqlite3.Connection:
    global _conn
    with _lock:
        if _conn is None:
            Path(settings.db_path).parent.mkdir(parents=True, exist_ok=True)
            _conn = sqlite3.connect(settings.db_path, check_same_thread=False)
            _conn.row_factory = sqlite3.Row
            _conn.execute("PRAGMA journal_mode=WAL")
            _conn.executescript(SCHEMA)
            _conn.commit()
        return _conn


def reset() -> None:
    """Drop everything. Used by `make seed` and the test suite."""
    global _conn
    with _lock:
        conn = connect()
        for t in ("a2a_tasks", "checkpoints", "cases", "case_notes",
                  "refund_ledger", "audit"):
            conn.execute(f"DELETE FROM {t}")
        conn.commit()


def _exec(sql: str, args: tuple = ()) -> sqlite3.Cursor:
    with _lock:
        conn = connect()
        cur = conn.execute(sql, args)
        conn.commit()
        return cur


# -- A2A task store --------------------------------------------------------


def put_task(task: dict) -> None:
    now = time.time()
    _exec(
        """INSERT INTO a2a_tasks
             (id, context_id, agent, state, payload, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?)
           ON CONFLICT(id) DO UPDATE SET
             state=excluded.state, payload=excluded.payload,
             updated_at=excluded.updated_at""",
        (task["id"], task.get("contextId", ""), task.get("agent", ""),
         task["status"]["state"], json.dumps(task), now, now),
    )


def get_task(task_id: str) -> dict | None:
    row = _exec("SELECT payload FROM a2a_tasks WHERE id=?", (task_id,)).fetchone()
    return json.loads(row["payload"]) if row else None


def tasks_for_context(context_id: str) -> list[dict]:
    rows = _exec("SELECT payload FROM a2a_tasks WHERE context_id=? ORDER BY created_at",
                 (context_id,)).fetchall()
    return [json.loads(r["payload"]) for r in rows]


# -- graph checkpoints -----------------------------------------------------


def save_checkpoint(thread_id: str, node: str, state: dict) -> None:
    _exec(
        """INSERT INTO checkpoints (thread_id, node, state, updated_at) VALUES (?,?,?,?)
           ON CONFLICT(thread_id) DO UPDATE SET
             node=excluded.node, state=excluded.state, updated_at=excluded.updated_at""",
        (thread_id, node, json.dumps(state, default=str), time.time()),
    )


def load_checkpoint(thread_id: str) -> tuple[str, dict] | None:
    row = _exec("SELECT node, state FROM checkpoints WHERE thread_id=?",
                (thread_id,)).fetchone()
    return (row["node"], json.loads(row["state"])) if row else None


# -- cases -----------------------------------------------------------------


def save_case(case_id: str, context_id: str, status: str, record: dict) -> None:
    _exec(
        """INSERT INTO cases
             (case_id, context_id, status, record, updated_at)
           VALUES (?,?,?,?,?)
           ON CONFLICT(case_id) DO UPDATE SET
             status=excluded.status, record=excluded.record,
             updated_at=excluded.updated_at""",
        (case_id, context_id, status, json.dumps(record, default=str), time.time()),
    )


def load_case(case_id: str) -> dict | None:
    row = _exec("SELECT record FROM cases WHERE case_id=?", (case_id,)).fetchone()
    return json.loads(row["record"]) if row else None


def list_cases() -> list[dict]:
    rows = _exec("SELECT case_id, context_id, status, updated_at FROM cases "
                 "ORDER BY updated_at DESC").fetchall()
    return [dict(r) for r in rows]


def add_note(case_id: str, author: str, note: str) -> None:
    _exec("INSERT INTO case_notes (case_id, author, note, at) VALUES (?,?,?,?)",
          (case_id, author, note, time.time()))


def notes(case_id: str) -> list[dict]:
    rows = _exec("SELECT author, note, at FROM case_notes WHERE case_id=? ORDER BY id",
                 (case_id,)).fetchall()
    return [dict(r) for r in rows]


# -- money -----------------------------------------------------------------


def commit_refund(key: str, case_id: str, refund_ref: str, amount: float,
                  tender: str, approver: str | None) -> tuple[bool, dict]:
    """Idempotent by construction. A replayed message returns the first result
    rather than minting a second refund."""
    with _lock:
        existing = _exec("SELECT * FROM refund_ledger WHERE idempotency_key=?",
                         (key,)).fetchone()
        if existing:
            return False, dict(existing)
        _exec(
            """INSERT INTO refund_ledger
               (idempotency_key, case_id, refund_ref, amount, tender, approver, at)
               VALUES (?,?,?,?,?,?,?)""",
            (key, case_id, refund_ref, amount, tender, approver, time.time()),
        )
        row = _exec("SELECT * FROM refund_ledger WHERE idempotency_key=?",
                    (key,)).fetchone()
        return True, dict(row)


def ledger() -> list[dict]:
    rows = _exec("SELECT * FROM refund_ledger ORDER BY at").fetchall()
    return [dict(r) for r in rows]


# -- audit -----------------------------------------------------------------


def audit(actor: str, kind: str, *, target: str = "", detail: Any = "",
          context_id: str = "", trace_id: str = "") -> None:
    if not isinstance(detail, str):
        detail = json.dumps(detail, default=str)[:4000]
    _exec(
        """INSERT INTO audit (at, trace_id, context_id, actor, kind, target, detail)
           VALUES (?,?,?,?,?,?,?)""",
        (time.time(), trace_id, context_id, actor, kind, target, detail),
    )


def trail(context_id: str | None = None, limit: int = 500) -> list[dict]:
    if context_id:
        rows = _exec("SELECT * FROM audit WHERE context_id=? ORDER BY id LIMIT ?",
                     (context_id, limit)).fetchall()
    else:
        rows = _exec("SELECT * FROM audit ORDER BY id LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]
