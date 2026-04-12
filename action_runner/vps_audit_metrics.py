# file: action_runner/vps_audit_metrics.py
from __future__ import annotations

from pathlib import Path

from .vps_audit import VpsAuditAnalysis, parse_vps_audit_log


def write_vps_audit_metrics(*, analysis: VpsAuditAnalysis, metrics_path: str) -> str:
    parsed = parse_vps_audit_log(analysis.log_path)

    def metric_value(key: str, default: str = "NaN") -> str:
        value = parsed.get(key)
        return value if value not in {None, ""} else default

    level_value = {"ok": 0, "warning": 1, "critical": 2}.get(analysis.level, 3)
    warning_count = sum(1 for item in analysis.findings if item.severity == "warning")
    critical_count = sum(1 for item in analysis.findings if item.severity == "critical")

    lines = [
        "# HELP vps_host_audit_status VPS host audit status (0=ok,1=warning,2=critical).",
        "# TYPE vps_host_audit_status gauge",
        f'vps_host_audit_status{{host="vps"}} {level_value}',
        "# HELP vps_host_audit_findings_count Total findings count.",
        "# TYPE vps_host_audit_findings_count gauge",
        f'vps_host_audit_findings_count{{host="vps"}} {len(analysis.findings)}',
        "# HELP vps_host_audit_findings_count_by_severity Findings count by severity.",
        "# TYPE vps_host_audit_findings_count_by_severity gauge",
        f'vps_host_audit_findings_count_by_severity{{host="vps",severity="warning"}} {warning_count}',
        f'vps_host_audit_findings_count_by_severity{{host="vps",severity="critical"}} {critical_count}',
        "# HELP vps_host_root_disk_used_percent Root disk used percent.",
        "# TYPE vps_host_root_disk_used_percent gauge",
        f'vps_host_root_disk_used_percent{{host="vps"}} {metric_value("root_used_percent")}',
        "# HELP vps_host_root_inode_used_percent Root inode used percent.",
        "# TYPE vps_host_root_inode_used_percent gauge",
        f'vps_host_root_inode_used_percent{{host="vps"}} {metric_value("root_inode_used_percent")}',
        "# HELP vps_host_swap_used_mb Swap used in MB.",
        "# TYPE vps_host_swap_used_mb gauge",
        f'vps_host_swap_used_mb{{host="vps"}} {metric_value("swap_used_mb")}',
        "# HELP vps_host_docker_running_containers Running containers count.",
        "# TYPE vps_host_docker_running_containers gauge",
        f'vps_host_docker_running_containers{{host="vps"}} {metric_value("docker_running_containers", "0")}',
        "# HELP vps_host_docker_unhealthy_containers Unhealthy containers count.",
        "# TYPE vps_host_docker_unhealthy_containers gauge",
        f'vps_host_docker_unhealthy_containers{{host="vps"}} {metric_value("docker_unhealthy_containers", "0")}',
        "# HELP vps_host_docker_restarting_containers Restarting containers count.",
        "# TYPE vps_host_docker_restarting_containers gauge",
        f'vps_host_docker_restarting_containers{{host="vps"}} {metric_value("docker_restarting_containers", "0")}',
        "# HELP vps_host_reboot_required Reboot required flag.",
        "# TYPE vps_host_reboot_required gauge",
        f'vps_host_reboot_required{{host="vps"}} {1 if parsed.get("reboot_required") == "yes" else 0}',
        "# HELP vps_host_fail2ban_healthy Fail2ban active flag.",
        "# TYPE vps_host_fail2ban_healthy gauge",
        f'vps_host_fail2ban_healthy{{host="vps"}} {1 if parsed.get("unit_fail2ban_service_active") == "active" else 0}',
        "# HELP vps_host_docker_daemon_healthy Docker daemon reachable flag.",
        "# TYPE vps_host_docker_daemon_healthy gauge",
        f'vps_host_docker_daemon_healthy{{host="vps"}} {1 if parsed.get("docker_reachable") == "yes" else 0}',
        "# HELP vps_host_action_runner_healthy Action runner probe flag.",
        "# TYPE vps_host_action_runner_healthy gauge",
        f'vps_host_action_runner_healthy{{host="vps"}} {1 if parsed.get("action_runner_probe") == "ok" else 0}',
        "# HELP vps_host_prometheus_healthy Prometheus probe flag.",
        "# TYPE vps_host_prometheus_healthy gauge",
        f'vps_host_prometheus_healthy{{host="vps"}} {1 if parsed.get("prometheus_probe") == "ok" else 0}',
        "# HELP vps_host_alertmanager_healthy Alertmanager probe flag.",
        "# TYPE vps_host_alertmanager_healthy gauge",
        f'vps_host_alertmanager_healthy{{host="vps"}} {1 if parsed.get("alertmanager_probe") == "ok" else 0}',
        "# HELP vps_host_grafana_healthy Grafana probe flag.",
        "# TYPE vps_host_grafana_healthy gauge",
        f'vps_host_grafana_healthy{{host="vps"}} {1 if parsed.get("grafana_probe") == "ok" else 0}',
        "# HELP vps_host_tg_relay_healthy TG relay probe flag.",
        "# TYPE vps_host_tg_relay_healthy gauge",
        f'vps_host_tg_relay_healthy{{host="vps"}} {1 if parsed.get("tg_relay_probe") == "ok" else 0}',
        "# HELP vps_host_node_exporter_healthy Node exporter probe flag.",
        "# TYPE vps_host_node_exporter_healthy gauge",
        f'vps_host_node_exporter_healthy{{host="vps"}} {1 if parsed.get("node_exporter_probe") == "ok" else 0}',
        "# HELP vps_host_ufw_active UFW active flag.",
        "# TYPE vps_host_ufw_active gauge",
        f'vps_host_ufw_active{{host="vps"}} {1 if parsed.get("ufw_status") == "active" else 0}',
        "# HELP vps_host_tailscale_serve_ok Tailscale serve status flag.",
        "# TYPE vps_host_tailscale_serve_ok gauge",
        f'vps_host_tailscale_serve_ok{{host="vps"}} {1 if parsed.get("tailscale_serve_status") == "ok" else 0}',
    ]

    for port in ("3000", "3100", "9080", "9090", "9093"):
        lines.extend(
            [
                f"# HELP vps_host_tailscale_serve_port_{port} Tailscale serve port {port} present.",
                f"# TYPE vps_host_tailscale_serve_port_{port} gauge",
                f'vps_host_tailscale_serve_port_{port}{{host="vps"}} {1 if parsed.get(f"tailscale_serve_port_{port}") == "yes" else 0}',
            ]
        )

    for finding in analysis.findings:
        kind = finding.kind.replace('"', "").replace("\\", "_")
        severity = finding.severity.replace('"', "")
        lines.append(f'vps_host_audit_finding_present{{host="vps",kind="{kind}",severity="{severity}"}} 1')

    path = Path(metrics_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path)
