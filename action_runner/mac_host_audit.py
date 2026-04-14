from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_MAC_AUDIT_DIR = "/srv/control-plane/state/mac-host-audit"


@dataclass(frozen=True, slots=True)
class MacHostAuditFinding:
    severity: str
    kind: str
    message: str


@dataclass(frozen=True, slots=True)
class MacHostAuditAnalysis:
    level: str
    findings: list[MacHostAuditFinding]
    summary: str
    log_path: str


def save_mac_host_audit_snapshot(payload: dict[str, Any], *, audit_dir: str = DEFAULT_MAC_AUDIT_DIR) -> str:
    timestamp = str(payload.get("timestamp_utc", "")).strip()
    safe_stamp = (
        timestamp.replace(" UTC", "")
        .replace("-", "")
        .replace(":", "")
        .replace(" ", "_")
    )

    if not safe_stamp:
        safe_stamp = "unknown"

    target_dir = Path(audit_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    path = target_dir / f"audit_{safe_stamp}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    latest = target_dir / "latest.json"
    if latest.exists() or latest.is_symlink():
        latest.unlink()
    latest.symlink_to(path.name)

    return str(path)


def latest_mac_host_audit_path(*, audit_dir: str = DEFAULT_MAC_AUDIT_DIR) -> str | None:
    target_dir = Path(audit_dir)
    latest = target_dir / "latest.json"

    if latest.exists():
        return str(latest.resolve())

    candidates = sorted(target_dir.glob("audit_*.json"), key=lambda item: item.name, reverse=True)
    return str(candidates[0]) if candidates else None


def load_mac_host_audit_snapshot(log_path: str) -> dict[str, Any]:
    data = json.loads(Path(log_path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("mac host audit snapshot must be a JSON object")
    return data


def _as_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(float(value))
    except (TypeError, ValueError):
        return None


def analyze_mac_host_audit_snapshot(snapshot: dict[str, Any], *, log_path: str) -> MacHostAuditAnalysis:
    findings: list[MacHostAuditFinding] = []

    def add(severity: str, kind: str, message: str) -> None:
        findings.append(MacHostAuditFinding(severity=severity, kind=kind, message=message))

    memory_free_percent = _as_float(snapshot.get("memory_free_percent"))
    if memory_free_percent is not None:
        if memory_free_percent < 5:
            add("critical", "memory_pressure", f"memory free {memory_free_percent:.0f}%")
        elif memory_free_percent < 10:
            add("warning", "memory_pressure", f"memory free {memory_free_percent:.0f}%")

    swap_used_mb = _as_float(snapshot.get("swap_used_mb"))
    if swap_used_mb is not None:
        if swap_used_mb >= 8192:
            add("critical", "swap_high", f"swap used {swap_used_mb:.0f}MB")
        elif swap_used_mb >= 4096:
            add("warning", "swap_high", f"swap used {swap_used_mb:.0f}MB")

    disk_used_percent = _as_int(snapshot.get("disk_used_percent"))
    if disk_used_percent is not None:
        if disk_used_percent >= 92:
            add("critical", "disk_high", f"root disk used {disk_used_percent}%")
        elif disk_used_percent >= 85:
            add("warning", "disk_high", f"root disk used {disk_used_percent}%")

    battery_percent = _as_int(snapshot.get("battery_percent"))
    power_source = str(snapshot.get("power_source", "") or "unknown")
    if power_source == "battery" and battery_percent is not None:
        if battery_percent <= 10:
            add("critical", "battery_low", f"battery {battery_percent}% on battery power")
        elif battery_percent <= 20:
            add("warning", "battery_low", f"battery {battery_percent}% on battery power")

    brew_outdated_count = _as_int(snapshot.get("brew_outdated_count"))
    if brew_outdated_count is not None:
        if brew_outdated_count >= 30:
            add("warning", "brew_outdated", f"{brew_outdated_count} outdated brew packages")

    agent_loaded = snapshot.get("agent_launchd_loaded")
    agent_running = snapshot.get("agent_launchd_running")
    if agent_loaded is False:
        add("warning", "agent_launchd_missing", "mac memory guard launchd job not loaded")
    elif agent_loaded is True and agent_running is False:
        add("warning", "agent_launchd_not_running", "mac memory guard launchd job not running")

    tm_latest_backup = str(snapshot.get("tm_latest_backup", "") or "").strip()
    if not tm_latest_backup:
        add("warning", "timemachine_unknown", "time machine latest backup unavailable")

    if any(item.severity == "critical" for item in findings):
        level = "critical"
    elif findings:
        level = "warning"
    else:
        level = "ok"

    summary = "; ".join(f"{item.severity}:{item.message}" for item in findings) if findings else "ok:no findings"
    return MacHostAuditAnalysis(level=level, findings=findings, summary=summary, log_path=log_path)
