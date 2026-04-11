from __future__ import annotations

from .models import Evaluation, Metrics

WARNING_SWAP_MB = 1400.0
CRITICAL_SWAP_MB = 2400.0

WARNING_UPTIME_DAYS = 10.0
CRITICAL_UPTIME_DAYS = 20.0

WARNING_TOP_RSS_MB = 1800.0
CRITICAL_TOP_RSS_MB = 2400.0

WARNING_DISK_USED_PERCENT = 85
CRITICAL_DISK_USED_PERCENT = 92

HIGH_SWAP_MB = 1024.0
LOW_FREE_MEMORY_PERCENT = 20.0
VERY_LOW_FREE_MEMORY_PERCENT = 12.0


def normalize_app_name(command: str) -> str:
    command = command.strip()
    mappings = [
        ("ChatGPT.app", "ChatGPT"),
        ("Obsidian.app", "Obsidian"),
        ("iTerm.app", "iTerm"),
        ("iTerm2", "iTerm"),
        ("Music.app", "Music"),
        ("Safari.app", "Safari"),
        ("AppleSpell.service", "AppleSpell"),
        ("WindowServer", "WindowServer"),
        ("Notes.app", "Notes"),
        ("Telegram.app", "Telegram"),
        ("Cursor.app", "Cursor"),
        ("Code.app", "VSCode"),
    ]

    for needle, name in mappings:
        if needle in command:
            return name

    last = command.split("/")[-1]
    return last[:40] if last else (command[:40] if command else "unknown")


def evaluate(metrics: Metrics) -> Evaluation:
    status = "ok"
    reasons: list[str] = []

    if metrics.swap_used_mb is not None and metrics.swap_used_mb >= WARNING_SWAP_MB:
        status = "warning"
        reasons.append(f"swap {metrics.swap_used_mb:.0f}MB")

    if metrics.uptime_days is not None and metrics.uptime_days >= WARNING_UPTIME_DAYS:
        status = "warning"
        reasons.append(f"uptime {metrics.uptime_days:.1f}d")

    if metrics.top_processes and metrics.top_processes[0].rss_mb >= WARNING_TOP_RSS_MB:
        top = metrics.top_processes[0]
        status = "warning"
        reasons.append(f"{normalize_app_name(top.command)} {top.rss_mb:.0f}MB")

    if metrics.disk_used_percent is not None and metrics.disk_used_percent >= WARNING_DISK_USED_PERCENT:
        status = "warning"
        reasons.append(f"disk {metrics.disk_used_percent}%")

    if metrics.swap_used_mb is not None and metrics.swap_used_mb >= CRITICAL_SWAP_MB:
        status = "critical"
        reasons.append(f"critical swap {metrics.swap_used_mb:.0f}MB")

    if metrics.uptime_days is not None and metrics.uptime_days >= CRITICAL_UPTIME_DAYS:
        status = "critical"
        reasons.append(f"critical uptime {metrics.uptime_days:.1f}d")

    if metrics.top_processes and metrics.top_processes[0].rss_mb >= CRITICAL_TOP_RSS_MB:
        top = metrics.top_processes[0]
        status = "critical"
        reasons.append(f"critical {normalize_app_name(top.command)} {top.rss_mb:.0f}MB")

    if metrics.disk_used_percent is not None and metrics.disk_used_percent >= CRITICAL_DISK_USED_PERCENT:
        status = "critical"
        reasons.append(f"critical disk {metrics.disk_used_percent}%")

    if not reasons:
        reasons.append("system within thresholds")

    return Evaluation(status=status, reasons=reasons)


def suggested_action(metrics: Metrics, evaluation: Evaluation) -> str:
    top = metrics.top_processes[0] if metrics.top_processes else None
    has_top_process = top is not None

    swap_used_mb = metrics.swap_used_mb
    memory_free_percent = metrics.memory_free_percent
    disk_used_percent = metrics.disk_used_percent
    uptime_days = metrics.uptime_days
    top_rss_mb = top.rss_mb if top is not None else None

    if evaluation.status == "ok":
        return "none"

    if disk_used_percent is not None and disk_used_percent >= CRITICAL_DISK_USED_PERCENT:
        return "free_disk_space"

    if disk_used_percent is not None and disk_used_percent >= WARNING_DISK_USED_PERCENT:
        return "check_disk_usage"

    if evaluation.status == "critical":
        if has_top_process and top_rss_mb is not None and top_rss_mb >= CRITICAL_TOP_RSS_MB:
            return "soft_quit_top_candidate"

        if memory_free_percent is not None and memory_free_percent <= VERY_LOW_FREE_MEMORY_PERCENT:
            return "soft_quit_top_candidate"

        if swap_used_mb is not None and swap_used_mb >= CRITICAL_SWAP_MB:
            return "soft_quit_top_candidate"

        if uptime_days is not None and uptime_days >= CRITICAL_UPTIME_DAYS:
            return "reboot_if_persistent"

        return "soft_quit_top_candidate"

    if has_top_process and top_rss_mb is not None and top_rss_mb >= WARNING_TOP_RSS_MB:
        return "observe_or_quit_top_app"

    if swap_used_mb is not None and swap_used_mb >= HIGH_SWAP_MB:
        return "observe_or_quit_top_app"

    if memory_free_percent is not None and memory_free_percent <= LOW_FREE_MEMORY_PERCENT:
        return "observe_or_quit_top_app"

    if uptime_days is not None and uptime_days >= WARNING_UPTIME_DAYS:
        return "observe_or_reboot_later"

    return "observe"
