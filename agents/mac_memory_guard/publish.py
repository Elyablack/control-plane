from __future__ import annotations

import subprocess

from .evaluate import normalize_app_name
from .logging_utils import log_line
from .models import Evaluation, Metrics

REMOTE_PROM_HOST = "vps"
REMOTE_PROM_PATH = "/var/lib/node_exporter/textfile_collector/mac_memory.prom"
MAC_HOST_LABEL = "mba"


def run_cmd(cmd: list[str], *, check: bool = True) -> str:
    result = subprocess.run(cmd, capture_output=True, text=True, check=check)
    return result.stdout.strip()


def publish_metrics(metrics: Metrics, evaluation: Evaluation) -> bool:
    status_value = {"ok": 0, "warning": 1, "critical": 2}.get(evaluation.status, 3)
    top = metrics.top_processes[0] if metrics.top_processes else None
    top_name = normalize_app_name(top.command) if top else "none"
    top_rss_mb = top.rss_mb if top else 0.0

    prom_lines = [
        "# HELP mac_memory_status Mac memory status (0=ok, 1=warning, 2=critical).",
        "# TYPE mac_memory_status gauge",
        f'mac_memory_status{{host="{MAC_HOST_LABEL}"}} {status_value}',
        "# HELP mac_memory_free_percent System-wide memory free percentage from memory_pressure.",
        "# TYPE mac_memory_free_percent gauge",
        f'mac_memory_free_percent{{host="{MAC_HOST_LABEL}"}} {metrics.memory_free_percent if metrics.memory_free_percent is not None else "NaN"}',
        "# HELP mac_swap_used_mb Swap used in megabytes.",
        "# TYPE mac_swap_used_mb gauge",
        f'mac_swap_used_mb{{host="{MAC_HOST_LABEL}"}} {metrics.swap_used_mb if metrics.swap_used_mb is not None else "NaN"}',
        "# HELP mac_uptime_days Mac uptime in days.",
        "# TYPE mac_uptime_days gauge",
        f'mac_uptime_days{{host="{MAC_HOST_LABEL}"}} {metrics.uptime_days if metrics.uptime_days is not None else "NaN"}',
        "# HELP mac_disk_used_percent Root filesystem used percent.",
        "# TYPE mac_disk_used_percent gauge",
        f'mac_disk_used_percent{{host="{MAC_HOST_LABEL}"}} {metrics.disk_used_percent if metrics.disk_used_percent is not None else "NaN"}',
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
