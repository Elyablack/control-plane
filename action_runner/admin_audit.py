from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AuditFinding:
    severity: str
    message: str


@dataclass(frozen=True, slots=True)
class AuditAnalysis:
    overall: str
    findings: list[AuditFinding]
    log_path: str | None

    @property
    def exit_code(self) -> int:
        if self.overall == "critical":
            return 2
        return 0

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

    def add(severity: str, message: str) -> None:
        findings.append(AuditFinding(severity=severity, message=message))

    if "ip_ping: FAIL" in text:
        add("critical", "external ping failed")

    if "dns_resolve: FAIL" in text:
        add("critical", "dns resolution failed")

    if "ssh :22 not listening" in text:
        add("critical", "ssh not listening on port 22")

    smb_section = _extract_section(text, "SMB SERVICES", "BACKUP PATH")
    if _contains_any(smb_section, ["\nenabled\ninactive", "\ndisabled\ninactive", "smb ports not listening"]):
        add("critical", "smb service unhealthy")

    if "backup_path_exists: NO" in text:
        add("critical", "backup path missing")

    if "backup_path_writable: NO" in text:
        add("critical", "backup path not writable")

    network_services = _extract_section(text, "NETWORK + TAILSCALE", "SSH LISTEN")
    if _contains_any(network_services, ["\nenabled\ninactive", "\ndisabled\ninactive"]):
        add("critical", "tailscale or network service inactive")

    root_disk_percent = _extract_root_disk_percent(text)
    if root_disk_percent is not None:
        if root_disk_percent > 90:
            add("critical", f"root filesystem usage high ({root_disk_percent}%)")
        elif root_disk_percent > 80:
            add("warning", f"root filesystem usage elevated ({root_disk_percent}%)")

    root_inode_percent = _extract_root_inode_percent(text)
    if root_inode_percent is not None:
        if root_inode_percent > 90:
            add("critical", f"root inode usage high ({root_inode_percent}%)")
        elif root_inode_percent > 80:
            add("warning", f"root inode usage elevated ({root_inode_percent}%)")

    if "reboot_required: YES" in text:
        add("warning", "reboot required")

    upgradable_packages = _extract_first_int(r"upgradable_packages:\s*(\d+)", text)
    if upgradable_packages is not None and upgradable_packages > 0:
        add("warning", f"{upgradable_packages} upgradable packages")

    if "fail2ban inactive" in text:
        add("warning", "fail2ban inactive")

    if "crontab entry NOT found" in text:
        add("warning", "cron rsync entry missing")

    sysstat_section = _extract_section(text, "SYSSTAT (summary)", "CRON RSYNC (last 5 entries)")
    if _contains_any(sysstat_section, ['ENABLED="false"', "\ndisabled\n", "\ninactive\n"]):
        add("warning", "sysstat not healthy")

    if _contains_any(
        text,
        [
            "systemd-journald.service: Watchdog timeout",
            "Failed to start systemd-journald.service",
        ],
    ):
        add("warning", "recent journald watchdog/start failures detected")

    if _contains_any(
        text,
        [
            "brcmf_psm_watchdog_notify",
            "Invalid packet id",
        ],
    ):
        add("warning", "recent kernel wifi watchdog/errors detected")

    swap_used_mb = _extract_swap_used_mb(text)
    if swap_used_mb is not None and swap_used_mb > 512:
        add("warning", f"swap usage elevated ({swap_used_mb:.0f}MiB)")

    smart_section = _extract_section(text, "SMART HEALTH", "")
    if smart_section and "SMART overall-health self-assessment test result: PASSED".lower() not in smart_section.lower():
        add("warning", "smart health check not clearly passed")

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
    memory_section = _extract_section(text, "MEMORY + SWAP", "NETWORK + TAILSCALE")
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


def _contains_any(text: str, patterns: list[str]) -> bool:
    lowered = text.lower()
    return any(pattern.lower() in lowered for pattern in patterns)
