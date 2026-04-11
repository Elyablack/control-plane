from __future__ import annotations

from .client import complete_mac_task, fetch_mac_task, send_event_to_runner
from .collectors import collect_metrics
from .evaluate import evaluate, normalize_app_name
from .logging_utils import log_error, log_info
from .publish import publish_metrics
from .remediation import execute_mac_action


def collect_and_log():
    metrics = collect_metrics()
    evaluation = evaluate(metrics)
    top = metrics.top_processes[0] if metrics.top_processes else None
    top_name = normalize_app_name(top.command) if top else "none"
    top_rss_mb = f"{top.rss_mb:.0f}" if top else "n/a"

    log_info(
        "report_cycle_start",
        status=evaluation.status,
        swap_mb=metrics.swap_used_mb,
        mem_free=metrics.memory_free_percent,
        disk=metrics.disk_used_percent,
        top=top_name,
        top_rss_mb=top_rss_mb,
        timestamp_utc=metrics.timestamp_utc,
    )
    return metrics, evaluation


def run_report_cycle(*, publish_enabled: bool, force_event: bool) -> int:
    metrics, evaluation = collect_and_log()

    if publish_enabled:
        publish_metrics(metrics, evaluation)
        log_info("publish_metrics_ok")
    else:
        log_info("publish_metrics_skipped", reason="publish disabled")

    should_send_event = force_event or evaluation.status in {"warning", "critical"}
    if should_send_event:
        send_event_to_runner(metrics, evaluation)
        log_info(
            "runner_event_sent",
            status=evaluation.status,
            force_event=force_event,
        )
    else:
        log_info(
            "runner_event_skipped",
            status=evaluation.status,
            reason="status not warning/critical and force_event disabled",
        )

    log_info("report_cycle_end", status=evaluation.status)
    return 0


def run_worker_cycle() -> int:
    task = fetch_mac_task()
    if task is None:
        return 0

    task_id = task.get("id")
    task_type = task.get("task_type")

    log_info(
        "worker_task_received",
        task_id=task_id,
        task_type=task_type,
    )

    try:
        result = execute_mac_action(task)
        complete_mac_task(int(task["id"]), result)

        log_info(
            "worker_task_completed",
            task_id=task_id,
            task_type=task_type,
            result_status=result.get("status"),
            action=result.get("action"),
            target=result.get("target"),
            reason=result.get("reason"),
            error=result.get("error"),
        )
        return 0

    except Exception as exc:
        log_error(
            "worker_task_exception",
            task_id=task_id,
            task_type=task_type,
            error=str(exc),
        )
        raise
