from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class MonitoringStackAuditFinding:
    severity: str
    kind: str
    message: str


@dataclass(frozen=True, slots=True)
class MonitoringStackAuditAnalysis:
    level: str
    findings: list[MonitoringStackAuditFinding]
    summary: str
    log_path: str


CORE_CONTAINERS = (
    "prometheus",
    "alertmanager",
    "grafana",
    "loki",
    "tg_relay",
)

WARNING_CONTAINERS = (
    "promtail",
    "demo_app",
)

REQUIRED_TARGETS = (
    "nodes_vps",
    "nodes_admin",
    "action_runner",
)

OPTIONAL_TARGETS = (
    "demo_app",
)

HEALTHY_CONTAINER_STATES = {"running"}
HEALTHY_CONTAINER_HEALTH = {"healthy", "none", "", None}
HEALTHY_PROBE_VALUES = {"ok", "healthy", "up", "true", "1"}


def _parse_kv_lines(text: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("==="):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        parsed[key.strip()] = value.strip()
    return parsed


def _to_float(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _to_int(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except ValueError:
        return None


def _sanitize_metric_label(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in value.strip().lower()).strip("_")


def _metric_bool(value: bool) -> int:
    return 1 if value else 0


def _metric_status_code(level: str) -> int:
    if level == "critical":
        return 2
    if level == "warning":
        return 1
    return 0


def _probe_ok(value: str | None) -> bool:
    return (value or "").strip().lower() in HEALTHY_PROBE_VALUES


def _container_key_base(name: str) -> str:
    return f"container_{name}"


def _target_key_base(name: str) -> str:
    return f"prometheus_target_{name}"


def parse_monitoring_stack_audit_log(log_path: str) -> dict[str, str]:
    return _parse_kv_lines(Path(log_path).read_text(encoding="utf-8", errors="replace"))


def analyze_monitoring_stack_audit_log(log_path: str) -> MonitoringStackAuditAnalysis:
    data = parse_monitoring_stack_audit_log(log_path)
    findings: list[MonitoringStackAuditFinding] = []

    def add(severity: str, kind: str, message: str) -> None:
        findings.append(MonitoringStackAuditFinding(severity=severity, kind=kind, message=message))

    docker_inspect_failures = 0
    for name in ("prometheus", "alertmanager", "grafana", "loki", "promtail", "tg_relay", "demo_app"):
        key_base = _container_key_base(name)
        if data.get(f"{key_base}_status") == "inspect_failed":
            docker_inspect_failures += 1

    if docker_inspect_failures > 0:
        add("critical", "docker_inspect_unavailable", f"docker inspect failed for {docker_inspect_failures} containers")

    for name in CORE_CONTAINERS:
        key_base = _container_key_base(name)
        exists = data.get(f"{key_base}_exists")
        state = data.get(f"{key_base}_state")
        health = data.get(f"{key_base}_health")
        status = data.get(f"{key_base}_status")

        if status == "inspect_failed":
            continue

        if exists == "no":
            add("critical", f"{name}_missing", f"container {name} missing")
            continue

        if exists != "yes":
            add("critical", f"{name}_unknown", f"container {name} state unknown")
            continue

        if state not in HEALTHY_CONTAINER_STATES:
            add("critical", f"{name}_state", f"container {name} state {state or 'unknown'}")
            continue

        if health not in HEALTHY_CONTAINER_HEALTH:
            add("critical", f"{name}_health", f"container {name} health {health or 'unknown'}")

    for name in WARNING_CONTAINERS:
        key_base = _container_key_base(name)
        exists = data.get(f"{key_base}_exists")
        state = data.get(f"{key_base}_state")
        health = data.get(f"{key_base}_health")
        status = data.get(f"{key_base}_status")

        if status == "inspect_failed":
            continue

        if exists == "no":
            add("warning", f"{name}_missing", f"container {name} missing")
            continue

        if exists != "yes":
            add("warning", f"{name}_unknown", f"container {name} state unknown")
            continue

        if state not in HEALTHY_CONTAINER_STATES:
            add("warning", f"{name}_state", f"container {name} state {state or 'unknown'}")
            continue

        if health not in HEALTHY_CONTAINER_HEALTH:
            add("warning", f"{name}_health", f"container {name} health {health or 'unknown'}")

    core_probes = (
        ("probe_prometheus_ready", "prometheus_ready_probe", "prometheus ready probe failed"),
        ("probe_alertmanager_ready", "alertmanager_ready_probe", "alertmanager ready probe failed"),
        ("probe_grafana_health", "grafana_health_probe", "grafana health probe failed"),
        ("probe_loki_ready", "loki_ready_probe", "loki ready probe failed"),
        ("probe_tg_relay_ready", "tg_relay_ready_probe", "tg-relay ready probe failed"),
    )
    for key, kind, message in core_probes:
        if not _probe_ok(data.get(key)):
            add("critical", kind, message)

    warning_probes = (
        ("probe_promtail_ready", "promtail_ready_probe", "promtail ready probe failed"),
        ("probe_demo_app_health", "demo_app_health_probe", "demo-app health probe failed"),
    )
    for key, kind, message in warning_probes:
        if not _probe_ok(data.get(key)):
            add("warning", kind, message)

    if not _probe_ok(data.get("prometheus_query_api")):
        add("critical", "prometheus_query_api", "prometheus query API unavailable")

    for target_name in REQUIRED_TARGETS:
        value = _to_float(data.get(f"{_target_key_base(target_name)}_up"))
        if value is None:
            add("critical", f"{target_name}_target_unknown", f"required target {target_name} missing from audit")
        elif value < 1:
            add("critical", f"{target_name}_target_down", f"required target {target_name} down")

    for target_name in OPTIONAL_TARGETS:
        value = _to_float(data.get(f"{_target_key_base(target_name)}_up"))
        if value is None:
            add("warning", f"{target_name}_target_unknown", f"optional target {target_name} missing from audit")
        elif value < 1:
            add("warning", f"{target_name}_target_down", f"optional target {target_name} down")

    required_targets_down = _to_int(data.get("prometheus_required_targets_down"))
    if required_targets_down is not None and required_targets_down > 0:
        add("critical", "required_targets_down", f"{required_targets_down} required prometheus targets down")

    total_targets_down = _to_int(data.get("prometheus_total_targets_down"))
    if total_targets_down is not None and total_targets_down > 0 and (required_targets_down or 0) == 0:
        add("warning", "targets_down", f"{total_targets_down} prometheus targets down")

    demo_5xx_rate = _to_float(data.get("demo_app_5xx_rate"))
    if demo_5xx_rate is not None and demo_5xx_rate > 0:
        add("warning", "demo_app_5xx", f"demo-app 5xx rate {demo_5xx_rate:.4f}/s")

    demo_p95_latency = _to_float(data.get("demo_app_p95_latency_seconds"))
    if demo_p95_latency is not None and demo_p95_latency > 0.5:
        add("warning", "demo_app_latency", f"demo-app p95 latency {demo_p95_latency:.3f}s")

    container_restarting = _to_int(data.get("containers_restarting_total"))
    if container_restarting is not None and container_restarting > 0:
        add("warning", "containers_restarting", f"{container_restarting} containers restarting")

    if any(item.severity == "critical" for item in findings):
        level = "critical"
    elif findings:
        level = "warning"
    else:
        level = "ok"

    summary = "; ".join(f"{item.severity}:{item.message}" for item in findings) if findings else "ok:no findings"
    return MonitoringStackAuditAnalysis(level=level, findings=findings, summary=summary, log_path=log_path)


def render_monitoring_stack_audit_metrics(
    analysis: MonitoringStackAuditAnalysis,
    *,
    log_data: dict[str, str] | None = None,
    host: str = "vps",
) -> str:
    data = log_data or parse_monitoring_stack_audit_log(analysis.log_path)
    lines: list[str] = []

    def add_metric(name: str, value: int | float, labels: dict[str, str] | None = None) -> None:
        if labels:
            rendered_labels = ",".join(f'{key}="{value}"' for key, value in sorted(labels.items()))
            lines.append(f"{name}{{{rendered_labels}}} {value}")
        else:
            lines.append(f"{name} {value}")

    base_labels = {"host": host}

    add_metric("monitoring_stack_audit_status", _metric_status_code(analysis.level), base_labels)
    add_metric("monitoring_stack_audit_findings_count", len(analysis.findings), base_labels)

    warning_count = sum(1 for item in analysis.findings if item.severity == "warning")
    critical_count = sum(1 for item in analysis.findings if item.severity == "critical")
    add_metric(
        "monitoring_stack_audit_findings_count_by_severity",
        warning_count,
        {**base_labels, "severity": "warning"},
    )
    add_metric(
        "monitoring_stack_audit_findings_count_by_severity",
        critical_count,
        {**base_labels, "severity": "critical"},
    )

    component_health_metrics = {
        "monitoring_stack_prometheus_healthy": (
            data.get("container_prometheus_exists") == "yes"
            and data.get("container_prometheus_state") == "running"
            and _probe_ok(data.get("probe_prometheus_ready"))
        ),
        "monitoring_stack_alertmanager_healthy": (
            data.get("container_alertmanager_exists") == "yes"
            and data.get("container_alertmanager_state") == "running"
            and _probe_ok(data.get("probe_alertmanager_ready"))
        ),
        "monitoring_stack_grafana_healthy": (
            data.get("container_grafana_exists") == "yes"
            and data.get("container_grafana_state") == "running"
            and _probe_ok(data.get("probe_grafana_health"))
        ),
        "monitoring_stack_loki_healthy": (
            data.get("container_loki_exists") == "yes"
            and data.get("container_loki_state") == "running"
            and _probe_ok(data.get("probe_loki_ready"))
        ),
        "monitoring_stack_promtail_healthy": (
            data.get("container_promtail_exists") == "yes"
            and data.get("container_promtail_state") == "running"
            and _probe_ok(data.get("probe_promtail_ready"))
        ),
        "monitoring_stack_tg_relay_healthy": (
            data.get("container_tg_relay_exists") == "yes"
            and data.get("container_tg_relay_state") == "running"
            and _probe_ok(data.get("probe_tg_relay_ready"))
        ),
        "monitoring_stack_demo_app_healthy": (
            data.get("container_demo_app_exists") == "yes"
            and data.get("container_demo_app_state") == "running"
            and _probe_ok(data.get("probe_demo_app_health"))
        ),
    }

    for metric_name, healthy in component_health_metrics.items():
        add_metric(metric_name, _metric_bool(healthy), base_labels)

    required_targets_down = _to_int(data.get("prometheus_required_targets_down")) or 0
    total_targets_down = _to_int(data.get("prometheus_total_targets_down")) or 0
    noncore_targets_down = max(total_targets_down - required_targets_down, 0)

    add_metric("monitoring_stack_core_targets_down", required_targets_down, base_labels)
    add_metric("monitoring_stack_noncore_targets_down", noncore_targets_down, base_labels)

    demo_5xx_rate = _to_float(data.get("demo_app_5xx_rate")) or 0.0
    demo_p95_latency = _to_float(data.get("demo_app_p95_latency_seconds")) or 0.0
    add_metric("monitoring_stack_demo_app_5xx_rate", demo_5xx_rate, base_labels)
    add_metric("monitoring_stack_demo_app_p95_latency_seconds", demo_p95_latency, base_labels)

    for item in analysis.findings:
        add_metric(
            "monitoring_stack_audit_finding_present",
            1,
            {
                **base_labels,
                "kind": _sanitize_metric_label(item.kind),
                "severity": item.severity,
            },
        )

    return "\n".join(lines).strip() + "\n"
