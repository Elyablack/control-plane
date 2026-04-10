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

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                alertname TEXT,
                fingerprint TEXT,
                severity TEXT,
                instance TEXT,
                job TEXT,
                status TEXT,
                summary TEXT,
                decision TEXT NOT NULL,
                reason TEXT NOT NULL,
                action TEXT,
                run_id INTEGER,
                created_at TEXT NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                decision_id INTEGER,
                task_type TEXT NOT NULL,
                payload TEXT NOT NULL,
                priority INTEGER NOT NULL DEFAULT 50,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                started_at TEXT,
                finished_at TEXT,
                result_json TEXT,
                error TEXT
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS scheduled_runs (
                schedule_name TEXT NOT NULL,
                slot_key TEXT NOT NULL,
                triggered_at TEXT NOT NULL,
                PRIMARY KEY (schedule_name, slot_key)
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

    return [
        {
            "id": row[0],
            "action": row[1],
            "trigger_type": row[2],
            "trigger_payload": row[3],
            "status": row[4],
            "started_at": row[5],
            "finished_at": row[6],
            "exit_code": row[7],
            "error": row[10],
        }
        for row in rows
    ]


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
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT last_executed_at
            FROM alert_cooldowns
            WHERE alert_key = ?
            """,
            (alert_key,),
        ).fetchone()

    return row[0] if row else None


def set_alert_execution(alert_key: str, ts: str) -> None:
    with get_conn() as conn:
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


def create_decision(
    *,
    source: str,
    alertname: str,
    fingerprint: str,
    severity: str,
    instance: str,
    job: str,
    status: str,
    summary: str,
    decision: str,
    reason: str,
    action: str | None,
    run_id: int | None,
    created_at: str,
) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO decisions (
                source,
                alertname,
                fingerprint,
                severity,
                instance,
                job,
                status,
                summary,
                decision,
                reason,
                action,
                run_id,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                source,
                alertname,
                fingerprint,
                severity,
                instance,
                job,
                status,
                summary,
                decision,
                reason,
                action,
                run_id,
                created_at,
            ),
        )
        conn.commit()
        return int(cur.lastrowid)


def list_decisions(limit: int = 50) -> list[dict]:
    with get_conn() as conn:
        cur = conn.execute(
            """
            SELECT id, source, alertname, fingerprint, severity, instance, job, status, summary, decision, reason, action, run_id, created_at
            FROM decisions
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = cur.fetchall()

    return [
        {
            "id": row[0],
            "source": row[1],
            "alertname": row[2],
            "fingerprint": row[3],
            "severity": row[4],
            "instance": row[5],
            "job": row[6],
            "status": row[7],
            "summary": row[8],
            "decision": row[9],
            "reason": row[10],
            "action": row[11],
            "run_id": row[12],
            "created_at": row[13],
        }
        for row in rows
    ]


def get_decision(decision_id: int) -> Optional[dict]:
    with get_conn() as conn:
        cur = conn.execute(
            """
            SELECT id, source, alertname, fingerprint, severity, instance, job, status, summary, decision, reason, action, run_id, created_at
            FROM decisions
            WHERE id = ?
            """,
            (decision_id,),
        )
        row = cur.fetchone()

    if row is None:
        return None

    return {
        "id": row[0],
        "source": row[1],
        "alertname": row[2],
        "fingerprint": row[3],
        "severity": row[4],
        "instance": row[5],
        "job": row[6],
        "status": row[7],
        "summary": row[8],
        "decision": row[9],
        "reason": row[10],
        "action": row[11],
        "run_id": row[12],
        "created_at": row[13],
    }


def create_task(
    *,
    decision_id: int | None,
    task_type: str,
    payload: str,
    priority: int,
    created_at: str,
) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO tasks (decision_id, task_type, payload, priority, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (decision_id, task_type, payload, priority, "pending", created_at),
        )
        conn.commit()
        return int(cur.lastrowid)


def list_tasks(limit: int = 50) -> list[dict]:
    with get_conn() as conn:
        cur = conn.execute(
            """
            SELECT id, decision_id, task_type, payload, priority, status, created_at, started_at, finished_at, result_json, error
            FROM tasks
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = cur.fetchall()

    return [
        {
            "id": row[0],
            "decision_id": row[1],
            "task_type": row[2],
            "payload": row[3],
            "priority": row[4],
            "status": row[5],
            "created_at": row[6],
            "started_at": row[7],
            "finished_at": row[8],
            "result_json": row[9],
            "error": row[10],
        }
        for row in rows
    ]


def get_task(task_id: int) -> Optional[dict]:
    with get_conn() as conn:
        cur = conn.execute(
            """
            SELECT id, decision_id, task_type, payload, priority, status, created_at, started_at, finished_at, result_json, error
            FROM tasks
            WHERE id = ?
            """,
            (task_id,),
        )
        row = cur.fetchone()

    if row is None:
        return None

    return {
        "id": row[0],
        "decision_id": row[1],
        "task_type": row[2],
        "payload": row[3],
        "priority": row[4],
        "status": row[5],
        "created_at": row[6],
        "started_at": row[7],
        "finished_at": row[8],
        "result_json": row[9],
        "error": row[10],
    }


def get_next_task(task_types: list[str]) -> Optional[dict]:
    if not task_types:
        return None

    placeholders = ",".join("?" for _ in task_types)

    with get_conn() as conn:
        cur = conn.execute(
            f"""
            SELECT id, decision_id, task_type, payload, priority, status, created_at
            FROM tasks
            WHERE status = 'pending'
              AND task_type IN ({placeholders})
            ORDER BY priority DESC, id ASC
            LIMIT 1
            """,
            task_types,
        )
        row = cur.fetchone()

    if row is None:
        return None

    return {
        "id": row[0],
        "decision_id": row[1],
        "task_type": row[2],
        "payload": row[3],
        "priority": row[4],
        "status": row[5],
        "created_at": row[6],
    }


def start_task(task_id: int, started_at: str) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE tasks
            SET status = 'running', started_at = ?
            WHERE id = ?
            """,
            (started_at, task_id),
        )
        conn.commit()


def finish_task(
    task_id: int,
    *,
    status: str,
    finished_at: str,
    result_json: str | None,
    error: str | None,
) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE tasks
            SET status = ?, finished_at = ?, result_json = ?, error = ?
            WHERE id = ?
            """,
            (status, finished_at, result_json, error, task_id),
        )
        conn.commit()


def has_scheduled_run(schedule_name: str, slot_key: str) -> bool:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT 1
            FROM scheduled_runs
            WHERE schedule_name = ? AND slot_key = ?
            LIMIT 1
            """,
            (schedule_name, slot_key),
        ).fetchone()

    return row is not None


def mark_scheduled_run(schedule_name: str, slot_key: str, triggered_at: str) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO scheduled_runs (schedule_name, slot_key, triggered_at)
            VALUES (?, ?, ?)
            """,
            (schedule_name, slot_key, triggered_at),
        )
        conn.commit()
