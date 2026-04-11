from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AuditFinding:
    severity: str
    kind: str
    message: str


@dataclass(frozen=True, slots=True)
class AuditAnalysis:
    overall: str
    findings: list[AuditFinding]
    log_path: str | None
    upgradable_packages: int
    wifi_watchdog_events: int
    reboot_required: bool
    reboot_detected_recently: bool
    boot_time_unixtime: int | None
    uptime_seconds: int | None
    timemachine_path_exists: bool
    timemachine_path_writable: bool
    infra_backups_path_exists: bool
    infra_backups_path_writable: bool
    infra_backups_tar_age_seconds: int | None
    infra_backups_sha_age_seconds: int | None
    infra_backups_tar_count: int
    infra_backups_sha_count: int
    infra_backups_pairs_match: bool
    smb_healthy: bool
    ssh_healthy: bool
    tailscale_healthy: bool
    fail2ban_healthy: bool
    root_disk_used_percent: int | None
    root_inode_used_percent: int | None
    timemachine_age_seconds: int | None
    audit_log_age_seconds: int | None

    @property
    def exit_code(self) -> int:
        if self.overall == "critical":
            return 2
        return 0

    def findings_count_by_severity(self, severity: str) -> int:
        return sum(1 for finding in self.findings if finding.severity == severity)

    def render_summary(self, *, host: str) -> str:
        parts = [
            f"host={host}",
            f"audit_analyze={self.overall}",
            f"findings={len(self.findings)}",
        ]
        if self.log_path:
            parts.append(f"log_path={self.log_path}")
        if self.findings:
            details = "; ".join(f"{f.severity}:{f.message}" for f in self.findings)
            parts.append(f"details={details}")
        return " ".join(parts)


def extract_log_path_from_prefixed_output(text: str) -> tuple[str | None, str]:
    log_path: str | None = None
    body_start_index: int | None = None
    lines = text.splitlines()

    for idx, line in enumerate(lines):
        if line.startswith("LOG_PATH:"):
            log_path = line.removeprefix("LOG_PATH:").strip() or None
        if line.strip() == "__AUDIT_BODY_BEGIN__":
            body_start_index = idx + 1
            break

    if body_start_index is None:
        return log_path, ""

    audit_text = "\n".join(lines[body_start_index:]).strip()
    return log_path, audit_text


def analyze_admin_audit_text(text: str, *, log_path: str | None = None) -> AuditAnalysis:
    findings: list[AuditFinding] = []

    def add(severity: str, kind: str, message: str) -> None:
        findings.append(AuditFinding(severity=severity, kind=kind, message=message))

    network_section = _extract_section(text, "NETWORK CHECK", "MEMORY + SWAP")
    network_services_section = _extract_section(text, "NETWORK + TAILSCALE", "SSH LISTEN")
    ssh_section = _extract_section(text, "SSH LISTEN", "UFW SUMMARY")
    fail2ban_section = _extract_section(text, "FAIL2BAN (status only)", "DISK ROOT")
    smb_section = _extract_section(text, "SMB SERVICES", "TIME MACHINE PATH")
    timemachine_path_section = _extract_section(text, "TIME MACHINE PATH", "TIME MACHINE FRESHNESS")
    infra_backups_path_section = _extract_section(text, "INFRA BACKUPS PATH", "INFRA BACKUPS FRESHNESS")
    sysstat_section = _extract_section(text, "SYSSTAT (summary)", "JOURNAL P3+ (current boot)")

    ssh_healthy = "ssh :22 not listening" not in ssh_section
    tailscale_healthy = _section_has_enabled_active_pair(network_services_section)
    fail2ban_healthy = "fail2ban inactive" not in fail2ban_section
    smb_healthy = _section_has_enabled_active_pair(smb_section) and "smb ports not listening" not in smb_section

    timemachine_path_exists = "timemachine_path_exists: YES" in timemachine_path_section
    timemachine_path_writable = "timemachine_path_writable: YES" in timemachine_path_section

    infra_backups_path_exists = "infra_backups_path_exists: YES" in infra_backups_path_section
    infra_backups_path_writable = "infra_backups_path_writable: YES" in infra_backups_path_section
    infra_backups_tar_age_seconds = _extract_nonnegative_int(r"infra_backups_tar_age_seconds:\s*(-?\d+)", text)
    infra_backups_sha_age_seconds = _extract_nonnegative_int(r"infra_backups_sha_age_seconds:\s*(-?\d+)", text)
    infra_backups_tar_count = _extract_first_int(r"infra_backups_tar_count:\s*(\d+)", text) or 0
    infra_backups_sha_count = _extract_first_int(r"infra_backups_sha_count:\s*(\d+)", text) or 0
    infra_backups_pairs_match = "infra_backups_pairs_match: YES" in text

    if "ip_ping: FAIL" in network_section:
        add("critical", "network_ping_failed", "external ping failed")

    if "dns_resolve: FAIL" in network_section:
        add("critical", "dns_resolution_failed", "dns resolution failed")

    if not ssh_healthy:
        add("critical", "ssh_unhealthy", "ssh not listening on port 22")

    if not tailscale_healthy:
        add("critical", "tailscale_unhealthy", "tailscale or network service inactive")

    if not smb_healthy:
        add("critical", "smb_unhealthy", "smb service unhealthy")

    if not timemachine_path_exists:
        add("critical", "timemachine_path_missing", "time machine path missing")

    if timemachine_path_exists and not timemachine_path_writable:
        add("critical", "timemachine_path_not_writable", "time machine path not writable")

    if not infra_backups_path_exists:
        add("warning", "infra_backups_path_missing", "infra-backups path missing")

    if infra_backups_path_exists and not infra_backups_path_writable:
        add("warning", "infra_backups_path_not_writable", "infra-backups path not writable")

    if not infra_backups_pairs_match:
        add("warning", "infra_backups_pairs_mismatch", "infra-backups tar/sha256 counts do not match")

    if infra_backups_tar_age_seconds is not None and infra_backups_tar_age_seconds > 3 * 24 * 3600:
        add(
            "warning",
            "infra_backups_stale",
            f"infra-backups latest archive is stale ({infra_backups_tar_age_seconds}s)",
        )

    root_disk_percent = _extract_root_disk_percent(text)
    if root_disk_percent is not None:
        if root_disk_percent > 90:
            add("critical", "root_disk_high", f"root filesystem usage high ({root_disk_percent}%)")
        elif root_disk_percent > 80:
            add("warning", "root_disk_elevated", f"root filesystem usage elevated ({root_disk_percent}%)")

    root_inode_percent = _extract_root_inode_percent(text)
    if root_inode_percent is not None:
        if root_inode_percent > 90:
            add("critical", "root_inode_high", f"root inode usage high ({root_inode_percent}%)")
        elif root_inode_percent > 80:
            add("warning", "root_inode_elevated", f"root inode usage elevated ({root_inode_percent}%)")

    reboot_required = "reboot_required: YES" in text
    if reboot_required:
        add("warning", "reboot_required", "reboot required")

    reboot_detected_recently = "reboot_detected_recently: YES" in text
    boot_time_unixtime = _extract_nonnegative_int(r"boot_time_unixtime:\s*(-?\d+)", text)
    uptime_seconds = _extract_nonnegative_int(r"uptime_seconds:\s*(-?\d+)", text)

    upgradable_packages = _extract_first_int(r"upgradable_packages:\s*(\d+)", text) or 0
    if upgradable_packages > 0:
        add("warning", "upgradable_packages", f"{upgradable_packages} upgradable packages")

    if not fail2ban_healthy:
        add("warning", "fail2ban_unhealthy", "fail2ban inactive")

    if _contains_any(
        sysstat_section,
        [
            'ENABLED="false"',
            "\ndisabled\n",
            "\ninactive\n",
        ],
    ):
        add("warning", "sysstat_unhealthy", "sysstat not healthy")

    if _contains_any(
        text,
        [
            "systemd-journald.service: Watchdog timeout",
            "Failed to start systemd-journald.service",
        ],
    ):
        add("warning", "journald_unstable", "recent journald watchdog/start failures detected")

    wifi_watchdog_events = _extract_wifi_watchdog_count(text)
    if wifi_watchdog_events >= 1:
        add("warning", "wifi_watchdog", f"broadcom wifi watchdog events detected ({wifi_watchdog_events} this boot)")

    swap_used_mb = _extract_swap_used_mb(text)
    if swap_used_mb is not None and swap_used_mb > 512:
        add("warning", "swap_elevated", f"swap usage elevated ({swap_used_mb:.0f}MiB)")

    smart_section = _extract_section(text, "SMART HEALTH", "")
    if smart_section and "SMART overall-health self-assessment test result: PASSED".lower() not in smart_section.lower():
        add("warning", "smart_unclear", "smart health check not clearly passed")

    timemachine_age_seconds = _extract_nonnegative_int(r"timemachine_age_seconds:\s*(-?\d+)", text)
    audit_log_age_seconds = _extract_nonnegative_int(r"audit_log_age_seconds:\s*(-?\d+)", text)

    overall = "ok"
    severities = {finding.severity for finding in findings}
    if "critical" in severities:
        overall = "critical"
    elif "warning" in severities:
        overall = "warning"

    return AuditAnalysis(
        overall=overall,
        findings=findings,
        log_path=log_path,
        upgradable_packages=upgradable_packages,
        wifi_watchdog_events=wifi_watchdog_events,
        reboot_required=reboot_required,
        reboot_detected_recently=reboot_detected_recently,
        boot_time_unixtime=boot_time_unixtime,
        uptime_seconds=uptime_seconds,
        timemachine_path_exists=timemachine_path_exists,
        timemachine_path_writable=timemachine_path_writable,
        infra_backups_path_exists=infra_backups_path_exists,
        infra_backups_path_writable=infra_backups_path_writable,
        infra_backups_tar_age_seconds=infra_backups_tar_age_seconds,
        infra_backups_sha_age_seconds=infra_backups_sha_age_seconds,
        infra_backups_tar_count=infra_backups_tar_count,
        infra_backups_sha_count=infra_backups_sha_count,
        infra_backups_pairs_match=infra_backups_pairs_match,
        smb_healthy=smb_healthy,
        ssh_healthy=ssh_healthy,
        tailscale_healthy=tailscale_healthy,
        fail2ban_healthy=fail2ban_healthy,
        root_disk_used_percent=root_disk_percent,
        root_inode_used_percent=root_inode_percent,
        timemachine_age_seconds=timemachine_age_seconds,
        audit_log_age_seconds=audit_log_age_seconds,
    )


def _extract_section(text: str, start_title: str, end_title: str) -> str:
    start_pattern = re.escape(f"==== {start_title} ====")
    if end_title:
        end_pattern = re.escape(f"==== {end_title} ====")
        pattern = rf"{start_pattern}(.*?){end_pattern}"
    else:
        pattern = rf"{start_pattern}(.*)$"

    match = re.search(pattern, text, flags=re.DOTALL)
    return match.group(1).strip() if match else ""


def _extract_first_int(pattern: str, text: str) -> int | None:
    match = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
    if not match:
        return None
    try:
        return int(match.group(1))
    except (TypeError, ValueError):
        return None


def _extract_nonnegative_int(pattern: str, text: str) -> int | None:
    value = _extract_first_int(pattern, text)
    if value is None or value < 0:
        return None
    return value


def _extract_root_disk_percent(text: str) -> int | None:
    disk_section = _extract_section(text, "DISK ROOT", "INODES")
    match = re.search(
        r"^/dev/\S+\s+\S+\s+\S+\s+\S+\s+\S+\s+(\d+)%\s+/$",
        disk_section,
        flags=re.MULTILINE,
    )
    return int(match.group(1)) if match else None


def _extract_root_inode_percent(text: str) -> int | None:
    inode_section = _extract_section(text, "INODES", "SYSSTAT (summary)")
    match = re.search(
        r"^/dev/\S+\s+\d+\s+\d+\s+\d+\s+(\d+)%\s+/$",
        inode_section,
        flags=re.MULTILINE,
    )
    return int(match.group(1)) if match else None


def _extract_swap_used_mb(text: str) -> float | None:
    memory_section = _extract_section(text, "MEMORY + SWAP", "BOOT STATE")
    match = re.search(
        r"^Swap:\s+\S+\s+(\S+)\s+\S+",
        memory_section,
        flags=re.MULTILINE,
    )
    if not match:
        return None

    raw = match.group(1).strip().lower()
    number_match = re.match(r"^([0-9]*\.?[0-9]+)([a-z]+)$", raw)
    if not number_match:
        return None

    value = float(number_match.group(1))
    unit = number_match.group(2)

    factor_by_unit = {
        "kib": 1 / 1024,
        "kb": 1 / 1000,
        "mib": 1,
        "mb": 1,
        "gib": 1024,
        "gb": 1000,
        "tib": 1024 * 1024,
        "tb": 1000 * 1000,
    }
    factor = factor_by_unit.get(unit)
    if factor is None:
        return None
    return value * factor


def _extract_wifi_watchdog_count(text: str) -> int:
    wifi_section = _extract_section(text, "WIFI WATCHDOG", "FAIL2BAN (status only)")
    journal_count = _extract_first_int(r"wifi_watchdog_events_journal_boot:\s*(\d+)", wifi_section) or 0
    dmesg_count = _extract_first_int(r"wifi_watchdog_events_dmesg_boot:\s*(\d+)", wifi_section) or 0
    return max(journal_count, dmesg_count)


def _contains_any(text: str, patterns: list[str]) -> bool:
    lowered = text.lower()
    return any(pattern.lower() in lowered for pattern in patterns)


def _section_has_enabled_active_pair(section: str) -> bool:
    lines = [line.strip().lower() for line in section.splitlines() if line.strip()]
    for idx in range(len(lines) - 1):
        if lines[idx] == "enabled" and lines[idx + 1] == "active":
            return True
    return False
