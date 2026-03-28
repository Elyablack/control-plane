from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Iterator, Optional

from .config import DB_PATH, STATE_DIR


def init_db() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action TEXT NOT NULL,
                trigger_type TEXT NOT NULL,
                trigger_payload TEXT,
                status TEXT NOT NULL,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                exit_code INTEGER,
                stdout TEXT,
                stderr TEXT,
                error TEXT
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS action_locks (
                action TEXT PRIMARY KEY,
                run_id INTEGER NOT NULL,
                acquired_at TEXT NOT NULL
            )
            """
        )

        conn.execute(
           """
           CREATE TABLE IF NOT EXISTS alert_cooldowns (
               alert_key TEXT PRIMARY KEY,
               last_executed_at TEXT NOT NULL
           )
           """
        )

        conn.commit()


@contextmanager
def get_conn() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(DB_PATH)
    try:
        yield conn
    finally:
        conn.close()


def create_run(action: str, trigger_type: str, trigger_payload: str, started_at: str) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO runs (action, trigger_type, trigger_payload, status, started_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (action, trigger_type, trigger_payload, "running", started_at),
        )
        conn.commit()
        return int(cur.lastrowid)


def finish_run(
    run_id: int,
    *,
    status: str,
    finished_at: str,
    exit_code: Optional[int],
    stdout: str,
    stderr: str,
    error: Optional[str],
) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE runs
            SET status = ?, finished_at = ?, exit_code = ?, stdout = ?, stderr = ?, error = ?
            WHERE id = ?
            """,
            (status, finished_at, exit_code, stdout, stderr, error, run_id),
        )
        conn.commit()


def _row_to_run(row: tuple) -> dict:
    return {
        "id": row[0],
        "action": row[1],
        "trigger_type": row[2],
        "trigger_payload": row[3],
        "status": row[4],
        "started_at": row[5],
        "finished_at": row[6],
        "exit_code": row[7],
        "stdout": row[8],
        "stderr": row[9],
        "error": row[10],
    }


def list_runs(limit: int = 20) -> list[dict]:
    with get_conn() as conn:
        cur = conn.execute(
            """
            SELECT id, action, trigger_type, trigger_payload, status, started_at, finished_at, exit_code, stdout, stderr, error
            FROM runs
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = cur.fetchall()

    runs = []
    for row in rows:
        run = _row_to_run(row)
        run.pop("stdout", None)
        run.pop("stderr", None)
        runs.append(run)
    return runs


def get_run(run_id: int) -> Optional[dict]:
    with get_conn() as conn:
        cur = conn.execute(
            """
            SELECT id, action, trigger_type, trigger_payload, status, started_at, finished_at, exit_code, stdout, stderr, error
            FROM runs
            WHERE id = ?
            """,
            (run_id,),
        )
        row = cur.fetchone()

    if row is None:
        return None
    return _row_to_run(row)

def acquire_action_lock(action: str, run_id: int, acquired_at: str) -> bool:
    with get_conn() as conn:
        try:
            conn.execute(
                """
                INSERT INTO action_locks (action, run_id, acquired_at)
                VALUES (?, ?, ?)
                """,
                (action, run_id, acquired_at),
            )
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False


def release_action_lock(action: str) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            DELETE FROM action_locks
            WHERE action = ?
            """,
            (action,),
        )
        conn.commit()


def get_action_lock(action: str) -> Optional[dict]:
    with get_conn() as conn:
        cur = conn.execute(
            """
            SELECT action, run_id, acquired_at
            FROM action_locks
            WHERE action = ?
            """,
            (action,),
        )
        row = cur.fetchone()

    if row is None:
        return None

    return {
        "action": row[0],
        "run_id": row[1],
        "acquired_at": row[2],
    }

def get_alert_last_execution(alert_key: str) -> str | None:
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT last_executed_at FROM alert_cooldowns WHERE alert_key = ?",
            (alert_key,),
        ).fetchone()
        return row[0] if row else None


def set_alert_execution(alert_key: str, ts: str) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO alert_cooldowns (alert_key, last_executed_at)
            VALUES (?, ?)
            ON CONFLICT(alert_key)
            DO UPDATE SET last_executed_at = excluded.last_executed_at
            """,
            (alert_key, ts),
        )
        conn.commit()
