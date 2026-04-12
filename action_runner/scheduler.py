from __future__ import annotations

import time
from datetime import datetime, timezone

from .executor import now_utc
from .schedule_loader import load_schedules
from .signal_service import process_signals
from .state import has_scheduled_run, mark_scheduled_run

SCHEDULER_POLL_INTERVAL_SECONDS = 30


def _now_dt_utc() -> datetime:
    return datetime.now(timezone.utc)


def _slot_key(now: datetime) -> str:
    return now.strftime("%Y-%m-%d %H:%M")


def _is_due(schedule: dict, now: datetime) -> bool:
    weekdays = schedule.get("weekdays", [])
    if not isinstance(weekdays, list):
        return False

    try:
        allowed_weekdays = {int(value) for value in weekdays}
    except (TypeError, ValueError):
        return False

    return (
        now.weekday() in allowed_weekdays
        and int(schedule["hour"]) == now.hour
        and int(schedule["minute"]) == now.minute
    )


def _build_signal(schedule: dict, slot_key: str) -> dict[str, str]:
    signal = dict(schedule["signal"])
    signal["fingerprint"] = f"schedule:{schedule['name']}:{slot_key}"
    return signal


def run_scheduler_tick() -> None:
    now = _now_dt_utc()
    slot_key = _slot_key(now)
    schedules = load_schedules()

    for schedule in schedules:
        if not schedule.get("enabled", True):
            continue

        if not _is_due(schedule, now):
            continue

        schedule_name = str(schedule["name"])

        if has_scheduled_run(schedule_name, slot_key):
            continue

        signal = _build_signal(schedule, slot_key)

        mark_scheduled_run(
            schedule_name=schedule_name,
            slot_key=slot_key,
            triggered_at=now_utc(),
        )

        process_signals([signal], source="scheduler")


def scheduler_loop() -> None:
    while True:
        try:
            run_scheduler_tick()
        except Exception:
            pass
        time.sleep(SCHEDULER_POLL_INTERVAL_SECONDS)
