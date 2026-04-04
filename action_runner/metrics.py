from __future__ import annotations

from datetime import datetime
from typing import Iterable

from .state import get_conn


PROMETHEUS_CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"


def _escape_label(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _labels(label_values: dict[str, str]) -> str:
    if not label_values:
        return ""
    parts = [f'{key}="{_escape_label(value)}"' for key, value in sorted(label_values.items())]
    return "{" + ",".join(parts) + "}"


def _metric_line(name: str, value: int | float, label_values: dict[str, str] | None = None) -> str:
    return f"{name}{_labels(label_values or {})} {value}"


def _parse_utc_to_unix(value: str | None) -> int:
    if not value:
        return 0
    try:
        return int(datetime.strptime(value, "%Y-%m-%d %H:%M:%S UTC").timestamp())
    except ValueError:
        return 0


def _fetchall(query: str, params: Iterable[object] = ()) -> list[tuple]:
    with get_conn() as conn:
        cur = conn.execute(query, tuple(params))
        return list(cur.fetchall())


def render_metrics() -> str:
    lines: list[str] = []

    lines.append("# HELP action_runner_decisions_total Total decisions by decision type.")
    lines.append("# TYPE action_runner_decisions_total counter")
    for decision, count in _fetchall(
        """
        SELECT decision, COUNT(*)
        FROM decisions
        GROUP BY decision
        ORDER BY decision
        """
    ):
        lines.append(
            _metric_line(
                "action_runner_decisions_total",
                int(count),
                {
                    "decision": str(decision),
                },
            )
        )

    lines.append("# HELP action_runner_tasks_total Total tasks by type and status.")
    lines.append("# TYPE action_runner_tasks_total counter")
    for task_type, status, count in _fetchall(
        """
        SELECT task_type, status, COUNT(*)
        FROM tasks
        GROUP BY task_type, status
        ORDER BY task_type, status
        """
    ):
        lines.append(
            _metric_line(
                "action_runner_tasks_total",
                int(count),
                {
                    "task_type": str(task_type),
                    "status": str(status),
                },
            )
        )

    lines.append("# HELP action_runner_runs_total Total action runs by action and status.")
    lines.append("# TYPE action_runner_runs_total counter")
    for action, status, count in _fetchall(
        """
        SELECT action, status, COUNT(*)
        FROM runs
        GROUP BY action, status
        ORDER BY action, status
        """
    ):
        lines.append(
            _metric_line(
                "action_runner_runs_total",
                int(count),
                {
                    "action": str(action),
                    "status": str(status),
                },
            )
        )

    lines.append("# HELP action_runner_mac_remediation_total Total remote mac remediation results.")
    lines.append("# TYPE action_runner_mac_remediation_total counter")
    for action, status, count in _fetchall(
        """
        SELECT
            COALESCE(json_extract(payload, '$.action'), ''),
            status,
            COUNT(*)
        FROM tasks
        WHERE task_type = 'mac_action'
        GROUP BY COALESCE(json_extract(payload, '$.action'), ''), status
        ORDER BY COALESCE(json_extract(payload, '$.action'), ''), status
        """
    ):
        lines.append(
            _metric_line(
                "action_runner_mac_remediation_total",
                int(count),
                {
                    "action": str(action),
                    "status": str(status),
                },
            )
        )

    lines.append("# HELP action_runner_queue_depth Current pending and running tasks by type.")
    lines.append("# TYPE action_runner_queue_depth gauge")
    for task_type, count in _fetchall(
        """
        SELECT task_type, COUNT(*)
        FROM tasks
        WHERE status IN ('pending', 'running')
        GROUP BY task_type
        ORDER BY task_type
        """
    ):
        lines.append(
            _metric_line(
                "action_runner_queue_depth",
                int(count),
                {
                    "task_type": str(task_type),
                },
            )
        )

    lines.append("# HELP action_runner_last_decision_unixtime Latest decision timestamp in unix seconds.")
    lines.append("# TYPE action_runner_last_decision_unixtime gauge")
    last_decision = _fetchall("SELECT MAX(created_at) FROM decisions")
    lines.append(
        _metric_line(
            "action_runner_last_decision_unixtime",
            _parse_utc_to_unix(last_decision[0][0] if last_decision else None),
        )
    )

    lines.append("# HELP action_runner_last_task_unixtime Latest task timestamp in unix seconds.")
    lines.append("# TYPE action_runner_last_task_unixtime gauge")
    last_task = _fetchall("SELECT MAX(created_at) FROM tasks")
    lines.append(
        _metric_line(
            "action_runner_last_task_unixtime",
            _parse_utc_to_unix(last_task[0][0] if last_task else None),
        )
    )

    lines.append("# HELP action_runner_last_run_unixtime Latest run timestamp in unix seconds.")
    lines.append("# TYPE action_runner_last_run_unixtime gauge")
    last_run = _fetchall("SELECT MAX(started_at) FROM runs")
    lines.append(
        _metric_line(
            "action_runner_last_run_unixtime",
            _parse_utc_to_unix(last_run[0][0] if last_run else None),
        )
    )

    return "\n".join(lines) + "\n"
