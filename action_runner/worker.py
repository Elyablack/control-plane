from __future__ import annotations

import json
import time
from typing import Any

from .config import DEFAULT_TASK_PRIORITY, TASK_PRIORITY_BY_SEVERITY
from .executor import execute_action, execute_chain, now_utc
from .state import create_task, finish_task, get_next_task, set_alert_execution, start_task

POLL_INTERVAL_SECONDS = 1


def _priority_for_severity(severity: str) -> int:
    return TASK_PRIORITY_BY_SEVERITY.get(severity.lower(), DEFAULT_TASK_PRIORITY)


def _queue_notify_task(*, decision_id: int | None, payload: dict[str, Any]) -> int:
    severity = str(payload.get("severity", "info")).strip().lower()
    priority = _priority_for_severity(severity)

    task_payload = {
        "action": "notify_tg",
        "payload": payload,
        "alert_key": None,
    }

    return create_task(
        decision_id=decision_id,
        task_type="notify",
        payload=json.dumps(task_payload, ensure_ascii=False, sort_keys=True),
        priority=priority,
        created_at=now_utc(),
    )


def _process_task(task: dict[str, Any]) -> dict[str, Any]:
    payload = json.loads(task["payload"])
    task_type = task["task_type"]

    if task_type == "chain":
        result = execute_chain(
            payload["steps"],
            trigger_type="task",
            chain_context=payload.get("chain_context", {}),
            queue_notify_task=lambda notify_payload: _queue_notify_task(
                decision_id=task.get("decision_id"),
                payload=notify_payload,
            ),
        )

        alert_key = payload.get("alert_key")
        if result.get("status") == "success" and isinstance(alert_key, str) and alert_key:
            set_alert_execution(alert_key, now_utc())

        return result

    if task_type in {"action", "notify"}:
        action = payload.get("action")
        action_payload = payload.get("payload", {})

        if not isinstance(action, str) or not action:
            raise ValueError("task payload is missing action")
        if not isinstance(action_payload, dict):
            raise ValueError("task payload field 'payload' must be an object")

        result = execute_action(
            action,
            action_payload,
            trigger_type="task",
        )

        alert_key = payload.get("alert_key")
        if result.get("status") == "success" and isinstance(alert_key, str) and alert_key:
            set_alert_execution(alert_key, now_utc())

        return result

    raise ValueError(f"unsupported task_type '{task_type}'")


def _run_task(task: dict[str, Any]) -> None:
    task_id = task["id"]
    start_task(task_id, now_utc())

    try:
        result = _process_task(task)
        finish_task(
            task_id,
            status=str(result.get("status", "failed")),
            finished_at=now_utc(),
            result_json=json.dumps(result, ensure_ascii=False, sort_keys=True),
            error=None,
        )
    except Exception as exc:
        finish_task(
            task_id,
            status="failed",
            finished_at=now_utc(),
            result_json=None,
            error=str(exc),
        )


def executor_worker_loop() -> None:
    while True:
        task = get_next_task(["chain", "action"])
        if task is None:
            time.sleep(POLL_INTERVAL_SECONDS)
            continue
        _run_task(task)


def notify_worker_loop() -> None:
    while True:
        task = get_next_task(["notify"])
        if task is None:
            time.sleep(POLL_INTERVAL_SECONDS)
            continue
        _run_task(task)
