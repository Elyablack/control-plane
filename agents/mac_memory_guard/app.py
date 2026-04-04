from __future__ import annotations

from .client import complete_mac_task, fetch_mac_task, send_event_to_runner
from .collectors import collect_metrics
from .evaluate import evaluate, normalize_app_name
from .logging_utils import log_line
from .publish import publish_metrics
from .remediation import execute_mac_action


def collect_and_log():
    metrics = collect_metrics()
    evaluation = evaluate(metrics)
    top = metrics.top_processes[0] if metrics.top_processes else None
    top_name = normalize_app_name(top.command) if top else "none"

    log_line("---- run start ----")
    log_line(
        "status="
        f"{evaluation.status} "
        f"swap_mb={metrics.swap_used_mb} "
        f"mem_free={metrics.memory_free_percent} "
        f"disk={metrics.disk_used_percent} "
        f"top={top_name}"
    )
    return metrics, evaluation


def run_report_cycle(*, publish_enabled: bool, force_event: bool) -> int:
    metrics, evaluation = collect_and_log()

    if publish_enabled:
        publish_metrics(metrics, evaluation)

    should_send_event = force_event or evaluation.status in {"warning", "critical"}
    if should_send_event:
        send_event_to_runner(metrics, evaluation)
    else:
        log_line("runner event: skipped (status=ok)")

    log_line("---- run end ----")
    return 0


def run_worker_cycle() -> int:
    log_line("---- worker run start ----")
    task = fetch_mac_task()
    if task is None:
        log_line("mac task: none")
        log_line("---- worker run end ----")
        return 0

    log_line(f"mac task received: id={task.get('id')} type={task.get('task_type')}")
    result = execute_mac_action(task)
    complete_mac_task(int(task["id"]), result)
    log_line("---- worker run end ----")
    return 0

