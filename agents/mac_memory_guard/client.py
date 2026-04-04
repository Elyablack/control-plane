from __future__ import annotations

import json
import subprocess
from typing import Any

from .evaluate import normalize_app_name
from .logging_utils import log_line
from .models import Evaluation, Metrics

ACTION_RUNNER_BASE_URL = "http://100.126.22.101:8088"
ACTION_RUNNER_ALERT_URL = f"{ACTION_RUNNER_BASE_URL}/events/alertmanager"
ACTION_RUNNER_MAC_NEXT_URL = f"{ACTION_RUNNER_BASE_URL}/tasks/mac/next"
ACTION_RUNNER_MAC_COMPLETE_URL = f"{ACTION_RUNNER_BASE_URL}/tasks/mac/complete"
MAC_HOST_LABEL = "mba"


def _description(metrics: Metrics, evaluation: Evaluation) -> str:
    top = metrics.top_processes[0] if metrics.top_processes else None
    top_name = normalize_app_name(top.command) if top else "none"
    top_rss = f"{top.rss_mb:.0f}MB" if top else "n/a"

    parts = [
        f"status={evaluation.status}",
        f"reasons={', '.join(evaluation.reasons)}",
        f"swap_mb={metrics.swap_used_mb:.0f}" if metrics.swap_used_mb is not None else "swap_mb=n/a",
        f"memory_free={metrics.memory_free_percent:.1f}%" if metrics.memory_free_percent is not None else "memory_free=n/a",
        f"uptime_days={metrics.uptime_days:.1f}" if metrics.uptime_days is not None else "uptime_days=n/a",
        f"disk_used={metrics.disk_used_percent}%" if metrics.disk_used_percent is not None else "disk_used=n/a",
        f"top_app={top_name}",
        f"top_rss={top_rss}",
        f"time={metrics.timestamp_utc}",
    ]
    return "\n".join(parts)


def send_event_to_runner(metrics: Metrics, evaluation: Evaluation) -> bool:
    payload = {
        "alerts": [
            {
                "status": "firing",
                "labels": {
                    "alertname": "MacMemoryPressure",
                    "severity": evaluation.status,
                    "instance": MAC_HOST_LABEL,
                    "job": "mac-agent",
                },
                "annotations": {
                    "summary": f"Mac memory pressure detected on {MAC_HOST_LABEL}",
                    "description": _description(metrics, evaluation),
                },
            }
        ]
    }

    try:
        result = subprocess.run(
            [
                "curl",
                "-fsS",
                ACTION_RUNNER_ALERT_URL,
                "--json",
                json.dumps(payload, ensure_ascii=False),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        log_line(f"runner event: ok response={result.stdout.strip()}")
        return True
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.strip() if exc.stderr else ""
        stdout = exc.stdout.strip() if exc.stdout else ""
        log_line(f"runner event: failed rc={exc.returncode} stdout={stdout} stderr={stderr}")
        return False


def fetch_mac_task() -> dict[str, Any] | None:
    try:
        result = subprocess.run(
            ["curl", "-fsS", ACTION_RUNNER_MAC_NEXT_URL],
            capture_output=True,
            text=True,
            check=True,
        )
        data = json.loads(result.stdout)
        task = data.get("task")
        if task is None:
            return None
        if not isinstance(task, dict):
            log_line("mac task fetch: invalid response")
            return None
        return task
    except Exception as exc:
        log_line(f"mac task fetch: failed error={exc}")
        return None


def complete_mac_task(task_id: int, result: dict[str, Any]) -> bool:
    payload = {
        "task_id": task_id,
        "status": result.get("status", "failed"),
        "result": result,
    }

    try:
        response = subprocess.run(
            [
                "curl",
                "-fsS",
                ACTION_RUNNER_MAC_COMPLETE_URL,
                "--json",
                json.dumps(payload, ensure_ascii=False),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        log_line(f"mac task complete: ok task_id={task_id} response={response.stdout.strip()}")
        return True
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.strip() if exc.stderr else ""
        stdout = exc.stdout.strip() if exc.stdout else ""
        log_line(
            f"mac task complete: failed task_id={task_id} rc={exc.returncode} stdout={stdout} stderr={stderr}"
        )
        return False
