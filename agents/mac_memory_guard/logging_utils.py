from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LOG_DIR = Path.home() / "logs"
LOG_FILE = LOG_DIR / "mac_memory_guard.log"


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso_utc() -> str:
    return now_utc().strftime("%Y-%m-%d %H:%M:%S UTC")


def ensure_dirs() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def _fmt_value(value: Any) -> str:
    if value is None:
        return "null"
    text = str(value).strip()
    if not text:
        return '""'
    if any(ch.isspace() for ch in text):
        return f'"{text}"'
    return text


def log_event(level: str, event: str, **fields: Any) -> None:
    ensure_dirs()
    parts = [f"level={level.upper()}", f"event={event}"]
    for key, value in fields.items():
        parts.append(f"{key}={_fmt_value(value)}")
    line = f"[{iso_utc()}] {' '.join(parts)}\n"
    LOG_FILE.open("a", encoding="utf-8").write(line)
    print(line, end="")


def log_info(event: str, **fields: Any) -> None:
    log_event("INFO", event, **fields)


def log_warn(event: str, **fields: Any) -> None:
    log_event("WARN", event, **fields)


def log_error(event: str, **fields: Any) -> None:
    log_event("ERROR", event, **fields)


def log_line(msg: str) -> None:
    log_info("message", text=msg)
