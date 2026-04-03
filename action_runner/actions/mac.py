from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from ..actions.types import ActionResult
from ..config import DEFAULT_TASK_PRIORITY, TASK_PRIORITY_BY_SEVERITY
from ..state import create_task


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _priority_for_severity(severity: str) -> int:
    return TASK_PRIORITY_BY_SEVERITY.get(severity.lower(), DEFAULT_TASK_PRIORITY)


def enqueue_mac_action(payload: dict[str, Any]) -> ActionResult:
    action = str(payload.get("action", "")).strip()
    severity = str(payload.get("severity", "critical")).strip().lower()
    instance = str(payload.get("instance", "")).strip()

    if not action:
        return ActionResult(
            status="failed",
            exit_code=1,
            stdout="",
            stderr="missing field: action",
            error="missing field: action",
        )

    task_payload = {
        "action": action,
        "instance": instance,
    }

    task_id = create_task(
        decision_id=None,
        task_type="mac_action",
        payload=json.dumps(task_payload, ensure_ascii=False, sort_keys=True),
        priority=_priority_for_severity(severity),
        created_at=now_utc(),
    )

    return ActionResult(
        status="success",
        exit_code=0,
        stdout=json.dumps({"task_id": task_id}, ensure_ascii=False),
        stderr="",
        error=None,
    )
