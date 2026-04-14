from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from .mac_host_audit import MacHostAuditAnalysis

DEFAULT_MAC_HOST_AUDIT_METRICS_PATH = "/var/lib/node_exporter/textfile_collector/mac_host_audit.prom"


def _bool_value(value: Any) -> int:
    return 1 if value is True else 0


def _num(value: Any) -> str:
    if value is None or value == "":
        return "NaN"
    try:
        return str(float(value))
    except (TypeError, ValueError):
        return "NaN"


def render_mac_host_audit_metrics(snapshot: dict[str, Any], analysis: MacHostAuditAnalysis) -> str:
    status_value = {"ok": 0, "warning": 1, "critical": 2}.get(analysis.level, 3)
    host = str(snapshot.get("host", "mba") or "mba")

    lines = [
        "# HELP mac_host_audit_last_run_unixtime Last mac host audit snapshot timestamp.",
        "# TYPE mac_host_audit_last_run_unixtime gauge",
        f'mac_host_audit_last_run_unixtime{{host="{host}"}} {_num(snapshot.get("timestamp_unix"))}',
        "# HELP mac_host_audit_analyzed_unixtime Last mac host audit analysis timestamp.",
        "# TYPE mac_host_audit_analyzed_unixtime gauge",
        f'mac_host_audit_analyzed_unixtime{{host="{host}"}} {int(time.time())}',
        "# HELP mac_host_audit_status Mac host audit status (0=ok, 1=warning, 2=critical).",
        "# TYPE mac_host_audit_status gauge",
        f'mac_host_audit_status{{host="{host}",level="{analysis.level}"}} {status_value}',
        "# HELP mac_host_audit_findings_count Mac host audit findings count.",
        "# TYPE mac_host_audit_findings_count gauge",
        f'mac_host_audit_findings_count{{host="{host}"}} {len(analysis.findings)}',
        "# HELP mac_host_audit_memory_free_percent Mac memory free percent.",
        "# TYPE mac_host_audit_memory_free_percent gauge",
        f'mac_host_audit_memory_free_percent{{host="{host}"}} {_num(snapshot.get("memory_free_percent"))}',
        "# HELP mac_host_audit_swap_used_mb Mac swap used megabytes.",
        "# TYPE mac_host_audit_swap_used_mb gauge",
        f'mac_host_audit_swap_used_mb{{host="{host}"}} {_num(snapshot.get("swap_used_mb"))}',
        "# HELP mac_host_audit_disk_used_percent Mac root disk used percent.",
        "# TYPE mac_host_audit_disk_used_percent gauge",
        f'mac_host_audit_disk_used_percent{{host="{host}"}} {_num(snapshot.get("disk_used_percent"))}',
        "# HELP mac_host_audit_battery_percent Mac battery percent.",
        "# TYPE mac_host_audit_battery_percent gauge",
        f'mac_host_audit_battery_percent{{host="{host}"}} {_num(snapshot.get("battery_percent"))}',
        "# HELP mac_host_audit_brew_outdated_count Mac Homebrew outdated package count.",
        "# TYPE mac_host_audit_brew_outdated_count gauge",
        f'mac_host_audit_brew_outdated_count{{host="{host}"}} {_num(snapshot.get("brew_outdated_count"))}',
        "# HELP mac_host_audit_timemachine_age_seconds Mac Time Machine latest backup age seconds.",
        "# TYPE mac_host_audit_timemachine_age_seconds gauge",
        f'mac_host_audit_timemachine_age_seconds{{host="{host}"}} {_num(snapshot.get("timemachine_age_seconds"))}',
        "# HELP mac_host_audit_agent_launchd_loaded Mac memory guard launchd loaded.",
        "# TYPE mac_host_audit_agent_launchd_loaded gauge",
        f'mac_host_audit_agent_launchd_loaded{{host="{host}"}} {_bool_value(snapshot.get("agent_launchd_loaded"))}',
        "# HELP mac_host_audit_agent_launchd_running Mac memory guard launchd running.",
        "# TYPE mac_host_audit_agent_launchd_running gauge",
        f'mac_host_audit_agent_launchd_running{{host="{host}"}} {_bool_value(snapshot.get("agent_launchd_running"))}',
        "# HELP mac_host_audit_finding_present Mac host audit finding presence by kind and severity.",
        "# TYPE mac_host_audit_finding_present gauge",
    ]

    for finding in analysis.findings:
        lines.append(
            f'mac_host_audit_finding_present{{host="{host}",kind="{finding.kind}",severity="{finding.severity}"}} 1'
        )

    return "\n".join(lines) + "\n"


def write_mac_host_audit_metrics(
    snapshot: dict[str, Any],
    analysis: MacHostAuditAnalysis,
    *,
    metrics_path: str = DEFAULT_MAC_HOST_AUDIT_METRICS_PATH,
) -> None:
    path = Path(metrics_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(render_mac_host_audit_metrics(snapshot, analysis), encoding="utf-8")
    tmp_path.replace(path)
