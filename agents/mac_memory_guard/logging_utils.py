from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

LOG_DIR = Path.home() / "logs"
LOG_FILE = LOG_DIR / "mac_memory_guard.log"


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso_utc() -> str:
    return now_utc().strftime("%Y-%m-%d %H:%M:%S UTC")


def ensure_dirs() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def log_line(msg: str) -> None:
    ensure_dirs()
    line = f"[{iso_utc()}] {msg}\n"
    LOG_FILE.open("a", encoding="utf-8").write(line)
    print(line, end="")

