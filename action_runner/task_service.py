from __future__ import annotations

import json

from .config import DEFAULT_TASK_PRIORITY, TASK_PRIORITY_BY_SEVERITY
from .executor import now_utc
from .state import create_task


def priority_for_severity(severity: str) -> int:
    return TASK_PRIORITY_BY_SEVERITY.get(severity.lower(), DEFAULT_TASK_PRIORITY)


def queue_notify_task(
    *,
    decision_id: int | None,
    severity: str,
    message: str,
    description: str,
    event: str,
    status: str = "firing",
    source: str = "action-runner",
) -> int:
    task_payload = {
        "action": "notify_tg",
        "payload": {
            "message": message,
            "description": description,
            "source": source,
            "event": event,
            "severity": severity,
            "status": status,
        },
        "alert_key": None,
    }

    return create_task(
        decision_id=decision_id,
        task_type="notify",
        payload=json.dumps(task_payload, ensure_ascii=False, sort_keys=True),
        priority=priority_for_severity(severity),
        created_at=now_utc(),
    )
