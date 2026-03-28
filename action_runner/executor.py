from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from .actions import ACTION_HANDLERS
from .config import ALLOWED_ACTIONS
from .state import create_run, finish_run


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def execute_action(action: str, payload: dict[str, Any], *, trigger_type: str) -> dict[str, Any]:
    if action not in ALLOWED_ACTIONS:
        raise ValueError(f"action '{action}' is not allowed")

    handler = ACTION_HANDLERS.get(action)
    if handler is None:
        raise ValueError(f"no handler registered for action '{action}'")

    started_at = now_utc()
    run_id = create_run(
        action=action,
        trigger_type=trigger_type,
        trigger_payload=json.dumps(payload, ensure_ascii=False, sort_keys=True),
        started_at=started_at,
    )

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

