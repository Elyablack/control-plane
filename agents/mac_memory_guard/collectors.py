from __future__ import annotations

import re
import subprocess
from datetime import datetime, timezone
from typing import List, Optional

from .models import Metrics, ProcessInfo


def run_cmd(cmd: List[str], *, check: bool = True) -> str:
    result = subprocess.run(cmd, capture_output=True, text=True, check=check)
    return result.stdout.strip()


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


def collect_metrics() -> Metrics:
    now = datetime.now(timezone.utc)
    return Metrics(
        timestamp_utc=now.strftime("%Y-%m-%d %H:%M:%S UTC"),
        timestamp_unix=int(now.timestamp()),
        memory_free_percent=parse_memory_pressure(),
        swap_used_mb=parse_swap_usage(),
        uptime_days=parse_uptime_days(),
        disk_used_percent=parse_disk_used_percent(),
        top_processes=parse_top_processes(),
    )

