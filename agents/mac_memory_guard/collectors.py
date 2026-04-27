from __future__ import annotations

import re
import subprocess
from datetime import datetime, timezone
from typing import List, Optional

from .models import MacAuditSnapshot, Metrics, ProcessInfo

MAC_HOST_LABEL = "mba"


def run_cmd(cmd: List[str], *, check: bool = True) -> str:
    result = subprocess.run(cmd, capture_output=True, text=True, check=check)
    return result.stdout.strip()


def run_cmd_optional(cmd: List[str]) -> str:
    try:
        return run_cmd(cmd, check=False)
    except Exception:
        return ""


def parse_memory_pressure() -> Optional[float]:
    out = run_cmd(["memory_pressure"])
    match = re.search(r"System-wide memory free percentage:\s+(\d+)%", out)
    return float(match.group(1)) if match else None


def parse_swap_usage() -> Optional[float]:
    out = run_cmd(["sysctl", "vm.swapusage"])
    match = re.search(r"used = ([0-9.]+)([MG])", out)
    if not match:
        return None

    value = float(match.group(1))
    unit = match.group(2)
    return value * 1024.0 if unit == "G" else value


def parse_uptime_days() -> Optional[float]:
    out = run_cmd(["uptime"])

    days_match = re.search(r"up\s+(\d+)\s+days?,\s+(\d+):(\d+)", out)
    if days_match:
        days = int(days_match.group(1))
        hours = int(days_match.group(2))
        minutes = int(days_match.group(3))
        return days + hours / 24.0 + minutes / 1440.0

    hm_match = re.search(r"up\s+(\d+):(\d+),", out)
    if hm_match:
        hours = int(hm_match.group(1))
        minutes = int(hm_match.group(2))
        return hours / 24.0 + minutes / 1440.0

    return None


def parse_disk_used_percent() -> Optional[int]:
    out = run_cmd(["df", "-h", "/"])
    lines = out.splitlines()
    if len(lines) < 2:
        return None

    parts = lines[1].split()
    if len(parts) < 5:
        return None

    try:
        return int(parts[4].rstrip("%"))
    except ValueError:
        return None


def parse_top_processes(limit: int = 5) -> List[ProcessInfo]:
    out = run_cmd(["ps", "-axo", "pid=,rss=,%mem=,args="])
    processes: List[ProcessInfo] = []

    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue

        parts = line.split(None, 3)
        if len(parts) < 4:
            continue

        try:
            pid = int(parts[0])
            rss_kb = int(parts[1])
            mem_percent = float(parts[2])
            command = parts[3]
        except ValueError:
            continue

        processes.append(
            ProcessInfo(
                pid=pid,
                rss_kb=rss_kb,
                mem_percent=mem_percent,
                command=command,
            )
        )

    processes.sort(key=lambda item: item.rss_kb, reverse=True)
    return processes[:limit]


def parse_battery_percent() -> Optional[int]:
    out = run_cmd_optional(["pmset", "-g", "batt"])
    match = re.search(r"(\d+)%", out)
    return int(match.group(1)) if match else None


def parse_power_source() -> str:
    out = run_cmd_optional(["pmset", "-g", "batt"])
    first_line = out.splitlines()[0].strip() if out.splitlines() else ""
    if "AC Power" in first_line:
        return "ac"
    if "Battery Power" in first_line:
        return "battery"
    return "unknown"


def parse_brew_outdated_count() -> Optional[int]:
    if not run_cmd_optional(["/usr/bin/which", "brew"]):
        return None

    out = run_cmd_optional(["brew", "outdated", "--quiet"])
    if not out.strip():
        return 0

    return len([line for line in out.splitlines() if line.strip()])


def parse_timemachine_latest_backup() -> Optional[str]:
    out = run_cmd_optional(["tmutil", "latestbackup"])
    return out.strip() or None


def parse_timemachine_age_seconds() -> Optional[int]:
    latest = parse_timemachine_latest_backup()
    if not latest:
        return None

    match = re.search(r"(\d{4}-\d{2}-\d{2}-\d{6})", latest)
    if not match:
        return None

    try:
        backup_time = datetime.strptime(match.group(1), "%Y-%m-%d-%H%M%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None

    return max(0, int(datetime.now(timezone.utc).timestamp() - backup_time.timestamp()))


def parse_agent_launchd_state() -> tuple[Optional[bool], Optional[bool]]:
    out = run_cmd_optional(["launchctl", "list"])
    if not out:
        return None, None

    expected_labels = {
        "com.elvira.mac-memory-worker",
        "com.elvira.mac-memory-report",
    }

    found = 0
    running = False

    for line in out.splitlines():
        parts = line.split()
        if len(parts) < 3:
            continue

        pid, _status, label = parts[0], parts[1], parts[2]
        if label not in expected_labels:
            continue

        found += 1
        if pid != "-":
            running = True

    return found == len(expected_labels), running


def collect_metrics() -> Metrics:
    now = datetime.now(timezone.utc)
    return Metrics(
        timestamp_utc=now.strftime("%Y-%m-%d %H:%M:%S UTC"),
        timestamp_unix=int(now.timestamp()),
        memory_free_percent=parse_memory_pressure(),
        swap_used_mb=parse_swap_usage(),
        uptime_days=parse_uptime_days(),
        disk_used_percent=parse_disk_used_percent(),
        battery_percent=parse_battery_percent(),
        power_source=parse_power_source(),
        top_processes=parse_top_processes(),
        brew_outdated_count=parse_brew_outdated_count(),
        tm_latest_backup=parse_timemachine_latest_backup(),
        timemachine_age_seconds=parse_timemachine_age_seconds(),
    )


def collect_mac_audit_snapshot() -> MacAuditSnapshot:
    metrics = collect_metrics()
    launchd_loaded, launchd_running = parse_agent_launchd_state()

    return MacAuditSnapshot(
        host=MAC_HOST_LABEL,
        timestamp_utc=metrics.timestamp_utc,
        timestamp_unix=metrics.timestamp_unix,
        memory_free_percent=metrics.memory_free_percent,
        swap_used_mb=metrics.swap_used_mb,
        uptime_days=metrics.uptime_days,
        disk_used_percent=metrics.disk_used_percent,
        battery_percent=metrics.battery_percent,
        power_source=metrics.power_source,
        tm_latest_backup=metrics.tm_latest_backup,
        timemachine_age_seconds=metrics.timemachine_age_seconds,
        brew_outdated_count=metrics.brew_outdated_count,
        agent_launchd_loaded=launchd_loaded,
        agent_launchd_running=launchd_running,
        top_processes=metrics.top_processes,
    )
