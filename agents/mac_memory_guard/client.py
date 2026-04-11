from __future__ import annotations

import json
import subprocess
from typing import Any

from .evaluate import evaluate, normalize_app_name, suggested_action
from .logging_utils import log_line
from .models import Evaluation, Metrics

ACTION_RUNNER_BASE_URL = "http://100.126.22.101:8088"
ACTION_RUNNER_ALERT_URL = f"{ACTION_RUNNER_BASE_URL}/events/alertmanager"
ACTION_RUNNER_MAC_NEXT_URL = f"{ACTION_RUNNER_BASE_URL}/tasks/mac/next"
ACTION_RUNNER_MAC_COMPLETE_URL = f"{ACTION_RUNNER_BASE_URL}/tasks/mac/complete"
MAC_HOST_LABEL = "mba"


def _top_process_fields(metrics: Metrics) -> tuple[str, str]:
    top = metrics.top_processes[0] if metrics.top_processes else None
    if top is None:
        return "none", "n/a"
    return normalize_app_name(top.command), f"{top.rss_mb:.0f}"


def _summary(metrics: Metrics, evaluation: Evaluation) -> str:
    top_app, top_rss_mb = _top_process_fields(metrics)
    swap_used_mb = f"{metrics.swap_used_mb:.0f}" if metrics.swap_used_mb is not None else "n/a"
    memory_free_percent = f"{metrics.memory_free_percent:.1f}" if metrics.memory_free_percent is not None else "n/a"

    return (
        f"{MAC_HOST_LABEL} memory pressure: "
        f"top={top_app} rss={top_rss_mb}MB "
        f"swap={swap_used_mb}MB free={memory_free_percent}%"
    )


def _description(metrics: Metrics, evaluation: Evaluation) -> str:
    top_app, top_rss_mb = _top_process_fields(metrics)
    action = suggested_action(metrics, evaluation)

    parts = [
        f"status={evaluation.status}",
        f"reasons={', '.join(evaluation.reasons)}" if evaluation.reasons else "reasons=none",
        f"swap_used_mb={metrics.swap_used_mb:.0f}" if metrics.swap_used_mb is not None else "swap_used_mb=n/a",
        f"memory_free_percent={metrics.memory_free_percent:.1f}" if metrics.memory_free_percent is not None else "memory_free_percent=n/a",
        f"uptime_days={metrics.uptime_days:.1f}" if metrics.uptime_days is not None else "uptime_days=n/a",
        f"disk_used_percent={metrics.disk_used_percent}" if metrics.disk_used_percent is not None else "disk_used_percent=n/a",
        f"top_app={top_app}",
        f"top_rss_mb={top_rss_mb}",
        f"suggested_action={action}",
        f"time={metrics.timestamp_utc}",
    ]
    return "\n".join(parts)


def _alert_annotations(metrics: Metrics, evaluation: Evaluation) -> dict[str, str]:
    top_app, top_rss_mb = _top_process_fields(metrics)
    action = suggested_action(metrics, evaluation)

    return {
        "summary": _summary(metrics, evaluation),
        "description": _description(metrics, evaluation),
        "top_app": top_app,
        "top_rss_mb": top_rss_mb,
        "swap_used_mb": f"{metrics.swap_used_mb:.0f}" if metrics.swap_used_mb is not None else "n/a",
        "memory_free_percent": (
            f"{metrics.memory_free_percent:.1f}" if metrics.memory_free_percent is not None else "n/a"
        ),
        "uptime_days": f"{metrics.uptime_days:.1f}" if metrics.uptime_days is not None else "n/a",
        "disk_used_percent": f"{metrics.disk_used_percent}" if metrics.disk_used_percent is not None else "n/a",
        "suggested_action": action,
        "reason_text": ", ".join(evaluation.reasons) if evaluation.reasons else "none",
        "timestamp_utc": metrics.timestamp_utc,
    }


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
                "annotations": _alert_annotations(metrics, evaluation),
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
