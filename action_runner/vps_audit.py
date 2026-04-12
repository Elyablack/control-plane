from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class VpsAuditFinding:
    severity: str
    kind: str
    message: str


@dataclass(frozen=True, slots=True)
class VpsAuditAnalysis:
    level: str
    findings: list[VpsAuditFinding]
    summary: str
    log_path: str


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


def parse_vps_audit_log(log_path: str) -> dict[str, str]:
    return _parse_kv_lines(Path(log_path).read_text(encoding="utf-8", errors="replace"))


def analyze_vps_audit_log(log_path: str) -> VpsAuditAnalysis:
    data = parse_vps_audit_log(log_path)
    findings: list[VpsAuditFinding] = []

    def add(severity: str, kind: str, message: str) -> None:
        findings.append(VpsAuditFinding(severity=severity, kind=kind, message=message))

    critical_units = {
        "docker.service": "docker",
        "prometheus-node-exporter.service": "node_exporter",
        "action-runner.service": "action_runner",
        "caddy.service": "caddy",
    }
    for unit_name, unit_label in critical_units.items():
        key = f"unit_{unit_name.replace('-', '_').replace('.', '_')}_active"
        active = data.get(key)
        if active != "active":
            add("critical", f"{unit_label}_unit", f"systemd unit {unit_name} is {active or 'unknown'}")

    if data.get("unit_fail2ban_service_active") not in {"active"}:
        add("warning", "fail2ban_inactive", "fail2ban inactive")

    if data.get("docker_reachable", "no") != "yes":
        add("critical", "docker_daemon_down", "docker daemon unreachable")

    for probe_name in (
        "prometheus_probe",
        "alertmanager_probe",
        "grafana_probe",
        "action_runner_probe",
        "node_exporter_probe",
    ):
        if data.get(probe_name) != "ok":
            add("critical", probe_name, f"{probe_name.removesuffix('_probe')} probe failed")

    if data.get("tg_relay_probe") != "ok":
        add("warning", "tg_relay_probe", "tg-relay probe failed")

    root_used_percent = _to_float(data.get("root_used_percent"))
    if root_used_percent is not None:
        if root_used_percent >= 92:
            add("critical", "root_disk_high", f"root disk used {root_used_percent:.0f}%")
        elif root_used_percent >= 85:
            add("warning", "root_disk_high", f"root disk used {root_used_percent:.0f}%")

    inode_used_percent = _to_float(data.get("root_inode_used_percent"))
    if inode_used_percent is not None:
        if inode_used_percent >= 92:
            add("critical", "root_inode_high", f"root inode used {inode_used_percent:.0f}%")
        elif inode_used_percent >= 85:
            add("warning", "root_inode_high", f"root inode used {inode_used_percent:.0f}%")

    swap_used_mb = _to_float(data.get("swap_used_mb"))
    if swap_used_mb is not None:
        if swap_used_mb >= 2048:
            add("critical", "swap_high", f"swap used {swap_used_mb:.0f}MB")
        elif swap_used_mb >= 1024:
            add("warning", "swap_high", f"swap used {swap_used_mb:.0f}MB")

    journal_p3_count = _to_int(data.get("journal_p3_count"))
    if journal_p3_count is not None and journal_p3_count >= 100:
        add("warning", "journal_errors", f"journal priority<=3 count {journal_p3_count}")

    if data.get("reboot_required") == "yes":
        add("warning", "reboot_required", "reboot required")

    unhealthy = _to_int(data.get("docker_unhealthy_containers")) or 0
    restarting = _to_int(data.get("docker_restarting_containers")) or 0

    if unhealthy >= 2:
        add("critical", "docker_unhealthy", f"{unhealthy} unhealthy containers")
    elif unhealthy >= 1:
        add("warning", "docker_unhealthy", f"{unhealthy} unhealthy containers")

    if restarting >= 1:
        add("warning", "docker_restarting", f"{restarting} restarting containers")

    critical_containers = ("prometheus", "alertmanager", "grafana", "tg-relay")
    for name in critical_containers:
        key_base = f"container_{name.replace('-', '_')}"
        exists = data.get(f"{key_base}_exists")
        state = data.get(f"{key_base}_state")
        health = data.get(f"{key_base}_health")

        if exists == "no":
            add("critical", f"{name}_missing", f"container {name} missing")
            continue

        if state not in {"running"}:
            add("critical", f"{name}_state", f"container {name} state {state or 'unknown'}")
        elif health not in {"healthy", "none", "", None}:
            add("critical", f"{name}_health", f"container {name} health {health}")

    demo_exists = data.get("container_demo_app_exists")
    demo_state = data.get("container_demo_app_state")
    demo_health = data.get("container_demo_app_health")
    if demo_exists == "yes":
        if demo_state not in {"running"}:
            add("warning", "demo_app_state", f"container demo-app state {demo_state or 'unknown'}")
        elif demo_health not in {"healthy", "none", "", None}:
            add("warning", "demo_app_health", f"container demo-app health {demo_health}")

    ufw_status = data.get("ufw_status")
    ufw_default_incoming = data.get("ufw_default_incoming")

    if ufw_status == "unknown":
        add("warning", "ufw_status_unavailable", "ufw status unavailable for audit")
    else:
        if ufw_status != "active":
            add("critical", "ufw_inactive", f"ufw status is {ufw_status or 'unknown'}")

        if ufw_default_incoming not in {"deny"}:
            add(
                "critical",
                "ufw_default_incoming",
                f"ufw incoming default is {ufw_default_incoming or 'unknown'}",
            )

        for port_key, label in (
            ("ufw_rule_22_present", "ssh"),
            ("ufw_rule_80_present", "http"),
            ("ufw_rule_443_present", "https"),
        ):
            value = data.get(port_key)
            if value == "no":
                add("warning", f"{label}_ufw_missing", f"ufw rule missing for {label}")

    tailscale_serve_status = data.get("tailscale_serve_status")
    if tailscale_serve_status not in {"ok"}:
        add("warning", "tailscale_serve_status", "tailscale serve status unavailable")
    else:
        for port in ("3000", "3100", "9080", "9090", "9093"):
            if data.get(f"tailscale_serve_port_{port}") != "yes":
                add("warning", f"tailscale_serve_{port}", f"tailscale serve missing port {port}")

    if any(item.severity == "critical" for item in findings):
        level = "critical"
    elif findings:
        level = "warning"
    else:
        level = "ok"

    summary = "; ".join(f"{item.severity}:{item.message}" for item in findings) if findings else "ok:no findings"
    return VpsAuditAnalysis(level=level, findings=findings, summary=summary, log_path=log_path)
