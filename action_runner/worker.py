from __future__ import annotations

import json
import time
from typing import Any

from .executor import execute_action, execute_chain, now_utc
from .state import finish_task, get_next_task, set_alert_execution, start_task

POLL_INTERVAL_SECONDS = 1


def _process_task(task: dict[str, Any]) -> dict[str, Any]:
    payload = json.loads(task["payload"])
    task_type = task["task_type"]

    if task_type == "chain":
        result = execute_chain(
            payload["steps"],
            trigger_type="task",
            chain_context=payload.get("chain_context", {}),
        )

        alert_key = payload.get("alert_key")
        if result.get("status") == "success" and alert_key:
            set_alert_execution(alert_key, now_utc())

        return result

    if task_type == "action":
        result = execute_action(
            payload["action"],
            payload.get("payload", {}),
            trigger_type="task",
        )

        alert_key = payload.get("alert_key")
        if result.get("status") == "success" and alert_key:
            set_alert_execution(alert_key, now_utc())

        return result

    raise ValueError(f"unsupported task_type {task_type}")


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


def _run_task(task: dict[str, Any]) -> None:
    task_id = task["id"]
    start_task(task_id, now_utc())

    try:
        result = _process_task(task)

        finish_task(
            task_id,
            status=result.get("status", "failed"),
            finished_at=now_utc(),
            result_json=json.dumps(result, ensure_ascii=False),
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
