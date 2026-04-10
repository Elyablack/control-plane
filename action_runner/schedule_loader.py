from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .config import SCHEDULES_PATH


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def load_schedules(path: Path | None = None) -> list[dict[str, Any]]:
    schedules_path = path or SCHEDULES_PATH

    if not schedules_path.exists():
        return []

    with schedules_path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    if not isinstance(raw, dict):
        raise ValueError("schedules file must contain a top-level object")

    schedules = _as_list(raw.get("schedules"))
    validated: list[dict[str, Any]] = []

    for idx, item in enumerate(schedules, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"schedule #{idx} must be an object")

        name = str(item.get("name", "")).strip()
        if not name:
            raise ValueError(f"schedule #{idx} is missing 'name'")

        enabled = bool(item.get("enabled", True))
        weekday = int(item.get("weekday", -1))
        hour = int(item.get("hour", -1))
        minute = int(item.get("minute", -1))
        signal = _as_dict(item.get("signal"))

        if weekday < 0 or weekday > 6:
            raise ValueError(f"schedule '{name}' weekday must be 0..6")
        if hour < 0 or hour > 23:
            raise ValueError(f"schedule '{name}' hour must be 0..23")
        if minute < 0 or minute > 59:
            raise ValueError(f"schedule '{name}' minute must be 0..59")
        if not signal:
            raise ValueError(f"schedule '{name}' must define non-empty signal")

        normalized_signal = {str(k): str(v) for k, v in signal.items()}
        required_keys = {"alertname", "status", "severity", "instance", "job", "summary", "description"}
        missing = [key for key in sorted(required_keys) if not normalized_signal.get(key)]
        if missing:
            raise ValueError(f"schedule '{name}' signal is missing required keys: {', '.join(missing)}")

        validated.append(
            {
                "name": name,
                "enabled": enabled,
                "weekday": weekday,
                "hour": hour,
                "minute": minute,
                "signal": normalized_signal,
            }
        )

    return validated
