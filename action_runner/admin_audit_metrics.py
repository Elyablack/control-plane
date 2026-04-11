# file: action_runner/admin_audit_metrics.py
from __future__ import annotations

from datetime import datetime, timezone

from .admin_audit import AuditAnalysis


def render_admin_audit_metrics(
    analysis: AuditAnalysis,
    *,
    host: str,
    now_unix: int | None = None,
) -> str:
    ts = now_unix if now_unix is not None else int(datetime.now(timezone.utc).timestamp())

    lines: list[str] = []

    lines.append("# HELP admin_host_audit_last_run_unixtime Unix timestamp of the last completed admin host audit.")
    lines.append("# TYPE admin_host_audit_last_run_unixtime gauge")
    lines.append(f'admin_host_audit_last_run_unixtime{{host="{host}"}} {ts}')

    lines.append("# HELP admin_host_audit_status Overall admin host audit status encoded as one-hot levels.")
    lines.append("# TYPE admin_host_audit_status gauge")
    for level in ("ok", "warning", "critical"):
        value = 1 if analysis.overall == level else 0
        lines.append(f'admin_host_audit_status{{host="{host}",level="{level}"}} {value}')

    lines.append("# HELP admin_host_audit_findings_count Total number of audit findings.")
    lines.append("# TYPE admin_host_audit_findings_count gauge")
    lines.append(f'admin_host_audit_findings_count{{host="{host}"}} {len(analysis.findings)}')

    lines.append("# HELP admin_host_audit_findings_count_by_severity Number of audit findings grouped by severity.")
    lines.append("# TYPE admin_host_audit_findings_count_by_severity gauge")
    for severity in ("warning", "critical"):
        count = analysis.findings_count_by_severity(severity)
        lines.append(f'admin_host_audit_findings_count_by_severity{{host="{host}",severity="{severity}"}} {count}')

    lines.append("# HELP admin_host_audit_upgradable_packages Number of upgradable packages detected by audit.")
    lines.append("# TYPE admin_host_audit_upgradable_packages gauge")
    lines.append(f'admin_host_audit_upgradable_packages{{host="{host}"}} {analysis.upgradable_packages}')

    lines.append("# HELP admin_host_audit_wifi_watchdog_events Broadcom Wi-Fi watchdog events seen in current boot.")
    lines.append("# TYPE admin_host_audit_wifi_watchdog_events gauge")
    lines.append(f'admin_host_audit_wifi_watchdog_events{{host="{host}"}} {analysis.wifi_watchdog_events}')

    lines.append("# HELP admin_host_audit_reboot_required Whether reboot-required marker is present.")
    lines.append("# TYPE admin_host_audit_reboot_required gauge")
    lines.append(f'admin_host_audit_reboot_required{{host="{host}"}} {1 if analysis.reboot_required else 0}')

    lines.append("# HELP admin_host_reboot_detected_recently Whether the node booted recently according to audit.")
    lines.append("# TYPE admin_host_reboot_detected_recently gauge")
    lines.append(f'admin_host_reboot_detected_recently{{host="{host}"}} {1 if analysis.reboot_detected_recently else 0}')

    if analysis.boot_time_unixtime is not None:
        lines.append("# HELP admin_host_boot_time_unixtime Boot time derived from /proc/uptime.")
        lines.append("# TYPE admin_host_boot_time_unixtime gauge")
        lines.append(f'admin_host_boot_time_unixtime{{host="{host}"}} {analysis.boot_time_unixtime}')

    if analysis.uptime_seconds is not None:
        lines.append("# HELP admin_host_uptime_seconds Uptime in seconds derived from /proc/uptime.")
        lines.append("# TYPE admin_host_uptime_seconds gauge")
        lines.append(f'admin_host_uptime_seconds{{host="{host}"}} {analysis.uptime_seconds}')

    lines.append("# HELP admin_host_audit_timemachine_path_exists Whether Time Machine path exists.")
    lines.append("# TYPE admin_host_audit_timemachine_path_exists gauge")
    lines.append(f'admin_host_audit_timemachine_path_exists{{host="{host}"}} {1 if analysis.timemachine_path_exists else 0}')

    lines.append("# HELP admin_host_audit_timemachine_path_writable Whether Time Machine path is writable.")
    lines.append("# TYPE admin_host_audit_timemachine_path_writable gauge")
    lines.append(f'admin_host_audit_timemachine_path_writable{{host="{host}"}} {1 if analysis.timemachine_path_writable else 0}')

    lines.append("# HELP admin_host_audit_smb_healthy Whether SMB service is healthy according to audit.")
    lines.append("# TYPE admin_host_audit_smb_healthy gauge")
    lines.append(f'admin_host_audit_smb_healthy{{host="{host}"}} {1 if analysis.smb_healthy else 0}')

    lines.append("# HELP admin_host_audit_ssh_healthy Whether SSH service is healthy according to audit.")
    lines.append("# TYPE admin_host_audit_ssh_healthy gauge")
    lines.append(f'admin_host_audit_ssh_healthy{{host="{host}"}} {1 if analysis.ssh_healthy else 0}')

    lines.append("# HELP admin_host_audit_tailscale_healthy Whether Tailscale/network service is healthy according to audit.")
    lines.append("# TYPE admin_host_audit_tailscale_healthy gauge")
    lines.append(f'admin_host_audit_tailscale_healthy{{host="{host}"}} {1 if analysis.tailscale_healthy else 0}')

    lines.append("# HELP admin_host_audit_fail2ban_healthy Whether fail2ban is healthy according to audit.")
    lines.append("# TYPE admin_host_audit_fail2ban_healthy gauge")
    lines.append(f'admin_host_audit_fail2ban_healthy{{host="{host}"}} {1 if analysis.fail2ban_healthy else 0}')

    if analysis.root_disk_used_percent is not None:
        lines.append("# HELP admin_host_audit_root_disk_used_percent Root filesystem used percent.")
        lines.append("# TYPE admin_host_audit_root_disk_used_percent gauge")
        lines.append(f'admin_host_audit_root_disk_used_percent{{host="{host}"}} {analysis.root_disk_used_percent}')

    if analysis.root_inode_used_percent is not None:
        lines.append("# HELP admin_host_audit_root_inode_used_percent Root inode used percent.")
        lines.append("# TYPE admin_host_audit_root_inode_used_percent gauge")
        lines.append(f'admin_host_audit_root_inode_used_percent{{host="{host}"}} {analysis.root_inode_used_percent}')

    if analysis.timemachine_age_seconds is not None:
        lines.append("# HELP admin_host_timemachine_age_seconds Age of the newest Time Machine sparsebundle artifact in seconds.")
        lines.append("# TYPE admin_host_timemachine_age_seconds gauge")
        lines.append(f'admin_host_timemachine_age_seconds{{host="{host}"}} {analysis.timemachine_age_seconds}')

    if analysis.audit_log_age_seconds is not None:
        lines.append("# HELP admin_host_audit_log_age_seconds Age of the newest audit log in seconds.")
        lines.append("# TYPE admin_host_audit_log_age_seconds gauge")
        lines.append(f'admin_host_audit_log_age_seconds{{host="{host}"}} {analysis.audit_log_age_seconds}')

    lines.append("# HELP admin_host_audit_finding_present Finding presence grouped by kind and severity.")
    lines.append("# TYPE admin_host_audit_finding_present gauge")
    seen_pairs = {(finding.kind, finding.severity) for finding in analysis.findings}
    for kind, severity in sorted(seen_pairs):
        lines.append(
            f'admin_host_audit_finding_present{{host="{host}",kind="{kind}",severity="{severity}"}} 1'
        )

    return "\n".join(lines) + "\n"
