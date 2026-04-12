from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .config import SCHEDULES_PATH


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _normalize_weekdays(item: dict[str, Any], name: str) -> list[int]:
    has_weekday = "weekday" in item
    has_weekdays = "weekdays" in item
    has_daily = bool(item.get("daily", False))

    mode_count = int(has_weekday) + int(has_weekdays) + int(has_daily)
    if mode_count > 1:
        raise ValueError(
            f"schedule '{name}' cannot define more than one of: weekday, weekdays, daily"
        )

    if has_daily:
        return [0, 1, 2, 3, 4, 5, 6]

    if has_weekdays:
        raw_weekdays = _as_list(item.get("weekdays"))
        if not raw_weekdays:
            raise ValueError(f"schedule '{name}' weekdays must be a non-empty list")

        normalized: list[int] = []
        for raw in raw_weekdays:
            try:
                value = int(raw)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"schedule '{name}' weekdays must contain only ints"
                ) from exc

            if value < 0 or value > 6:
                raise ValueError(
                    f"schedule '{name}' weekdays must contain values 0..6"
                )

            if value not in normalized:
                normalized.append(value)

        return normalized

    if has_weekday:
        try:
            value = int(item.get("weekday", -1))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"schedule '{name}' weekday must be int") from exc

        if value < 0 or value > 6:
            raise ValueError(f"schedule '{name}' weekday must be 0..6")

        return [value]

    raise ValueError(
        f"schedule '{name}' must define one of: weekday, weekdays, daily"
    )


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
        weekdays = _normalize_weekdays(item, name)

        try:
            hour = int(item.get("hour", -1))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"schedule '{name}' hour must be int") from exc

        try:
            minute = int(item.get("minute", -1))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"schedule '{name}' minute must be int") from exc

        signal = _as_dict(item.get("signal"))

        if hour < 0 or hour > 23:
            raise ValueError(f"schedule '{name}' hour must be 0..23")
        if minute < 0 or minute > 59:
            raise ValueError(f"schedule '{name}' minute must be 0..59")
        if not signal:
            raise ValueError(f"schedule '{name}' must define non-empty signal")

        normalized_signal = {str(k): str(v) for k, v in signal.items()}
        required_keys = {
            "alertname",
            "status",
            "severity",
            "instance",
            "job",
            "summary",
            "description",
        }
        missing = [key for key in sorted(required_keys) if not normalized_signal.get(key)]
        if missing:
            raise ValueError(
                f"schedule '{name}' signal is missing required keys: {', '.join(missing)}"
            )

        validated.append(
            {
                "name": name,
                "enabled": enabled,
                "weekdays": weekdays,
                "hour": hour,
                "minute": minute,
                "signal": normalized_signal,
            }
        )

    return validated
