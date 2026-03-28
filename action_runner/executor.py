from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from .actions import ACTION_HANDLERS
from .config import ALLOWED_ACTIONS
from .state import (
    acquire_action_lock,
    create_run,
    finish_run,
    get_action_lock,
    release_action_lock,
)


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def execute_action(action: str, payload: dict[str, Any], *, trigger_type: str) -> dict[str, Any]:
    if action not in ALLOWED_ACTIONS:
        raise ValueError(f"action '{action}' is not allowed")

    handler = ACTION_HANDLERS.get(action)
    if handler is None:
        raise ValueError(f"no handler registered for action '{action}'")

    started_at = now_utc()

    existing_lock = get_action_lock(action)
    if existing_lock is not None:
        return {
            "run_id": None,
            "action": action,
            "status": "blocked",
            "reason": "action is already running",
            "locked_by_run_id": existing_lock["run_id"],
            "acquired_at": existing_lock["acquired_at"],
        }

    run_id = create_run(
        action=action,
        trigger_type=trigger_type,
        trigger_payload=json.dumps(payload, ensure_ascii=False, sort_keys=True),
        started_at=started_at,
    )

    lock_acquired = acquire_action_lock(action, run_id, started_at)
    if not lock_acquired:
        finish_run(
            run_id,
            status="blocked",
            finished_at=now_utc(),
            exit_code=None,
            stdout="",
            stderr="",
            error="action lock could not be acquired",
        )
        return {
            "run_id": run_id,
            "action": action,
            "status": "blocked",
            "reason": "action lock could not be acquired",
            "detail_url": f"/runs/{run_id}",
        }

    try:
        result = handler(payload)

        finished_at = now_utc()
        status = "success" if result.returncode == 0 else "failed"
        error = None if result.returncode == 0 else f"command exited with code {result.returncode}"

        finish_run(
            run_id,
            status=status,
            finished_at=finished_at,
            exit_code=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            error=error,
        )

        return {
            "run_id": run_id,
            "action": action,
            "status": status,
            "started_at": started_at,
            "finished_at": finished_at,
            "exit_code": result.returncode,
            "detail_url": f"/runs/{run_id}",
        }
    finally:
        release_action_lock(action)
