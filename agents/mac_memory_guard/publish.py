# agents/mac_memory_guard/publish.py
from __future__ import annotations

import json
import os
import subprocess
import urllib.error
import urllib.request

from .evaluate import normalize_app_name
from .logging_utils import log_line
from .models import Evaluation, MacAuditSnapshot, Metrics

REMOTE_PROM_HOST = "vps"
REMOTE_PROM_PATH = "/var/lib/node_exporter/textfile_collector/mac_memory.prom"
MAC_HOST_LABEL = "mba"
RUNNER_URL = os.environ.get("ACTION_RUNNER_URL", "http://vps:8088").rstrip("/")


def run_cmd(cmd: list[str], *, check: bool = True) -> str:
    result = subprocess.run(cmd, capture_output=True, text=True, check=check)
    return result.stdout.strip()


def _num(value: object) -> str:
    if value is None or value == "":
        return "NaN"
    try:
        return str(float(value))
    except (TypeError, ValueError):
        return "NaN"


def publish_metrics(metrics: Metrics, evaluation: Evaluation) -> bool:
    status_value = {"ok": 0, "warning": 1, "critical": 2}.get(evaluation.status, 3)
    top = metrics.top_processes[0] if metrics.top_processes else None
    top_name = normalize_app_name(top.command) if top else "none"
    top_rss_mb = top.rss_mb if top else 0.0
    power_source = metrics.power_source if metrics.power_source in {"ac", "battery", "unknown"} else "unknown"

    prom_lines = [
        "# HELP mac_memory_status Mac memory status (0=ok, 1=warning, 2=critical).",
        "# TYPE mac_memory_status gauge",
        f'mac_memory_status{{host="{MAC_HOST_LABEL}"}} {status_value}',
        "# HELP mac_memory_free_percent System-wide memory free percentage from memory_pressure.",
        "# TYPE mac_memory_free_percent gauge",
        f'mac_memory_free_percent{{host="{MAC_HOST_LABEL}"}} {_num(metrics.memory_free_percent)}',
        "# HELP mac_swap_used_mb Swap used in megabytes.",
        "# TYPE mac_swap_used_mb gauge",
        f'mac_swap_used_mb{{host="{MAC_HOST_LABEL}"}} {_num(metrics.swap_used_mb)}',
        "# HELP mac_uptime_days Mac uptime in days.",
        "# TYPE mac_uptime_days gauge",
        f'mac_uptime_days{{host="{MAC_HOST_LABEL}"}} {_num(metrics.uptime_days)}',
        "# HELP mac_disk_used_percent Root filesystem used percent.",
        "# TYPE mac_disk_used_percent gauge",
        f'mac_disk_used_percent{{host="{MAC_HOST_LABEL}"}} {_num(metrics.disk_used_percent)}',
        "# HELP mac_battery_percent Mac battery percent.",
        "# TYPE mac_battery_percent gauge",
        f'mac_battery_percent{{host="{MAC_HOST_LABEL}"}} {_num(metrics.battery_percent)}',
        "# HELP mac_power_source Mac current power source (1=current source).",
        "# TYPE mac_power_source gauge",
        f'mac_power_source{{host="{MAC_HOST_LABEL}",source="ac"}} {1 if power_source == "ac" else 0}',
        f'mac_power_source{{host="{MAC_HOST_LABEL}",source="battery"}} {1 if power_source == "battery" else 0}',
        f'mac_power_source{{host="{MAC_HOST_LABEL}",source="unknown"}} {1 if power_source == "unknown" else 0}',
        "# HELP mac_top_process_rss_mb Top process RSS in megabytes.",
        "# TYPE mac_top_process_rss_mb gauge",
        f'mac_top_process_rss_mb{{host="{MAC_HOST_LABEL}",process="{top_name}"}} {top_rss_mb:.2f}',
        "# HELP mac_memory_last_run_unixtime Last successful run timestamp.",
        "# TYPE mac_memory_last_run_unixtime gauge",
        f'mac_memory_last_run_unixtime{{host="{MAC_HOST_LABEL}"}} {metrics.timestamp_unix}',
    ]
    prom_text = "\n".join(prom_lines) + "\n"

    remote_cmd = (
        "sudo mkdir -p /var/lib/node_exporter/textfile_collector && "
        f"cat <<'EOF' | sudo tee {REMOTE_PROM_PATH} >/dev/null\n"
        f"{prom_text}"
        "EOF"
    )

    try:
        run_cmd(["ssh", REMOTE_PROM_HOST, remote_cmd])
        log_line("publish: ok")
        return True
    except subprocess.CalledProcessError as exc:
        log_line(f"publish: failed: {exc}")
        return False


def publish_mac_host_audit(snapshot: MacAuditSnapshot) -> bool:
    body = json.dumps(snapshot.to_dict(), ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{RUNNER_URL}/events/mac-host-audit",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json; charset=utf-8"},
    )

    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            response.read()
        log_line("mac_host_audit_publish: ok")
        return True
    except urllib.error.URLError as exc:
        log_line(f"mac_host_audit_publish: failed: {exc}")
        return False
