from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from .config import ACTION_COOLDOWNS_SECONDS
from .state import get_alert_last_execution


def _parse_ts(ts: str) -> datetime:
    return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S UTC").replace(tzinfo=timezone.utc)


def decide_alert_action(alert: dict[str, Any]) -> dict[str, Any]:
    alertname = str(alert.get("alertname", "")).strip()
    status = str(alert.get("status", "")).strip().lower()
    fingerprint = str(alert.get("fingerprint", "")).strip()

    if alertname == "BackupMissing" and status == "firing":
        action = "run_backup"
        alert_key = fingerprint or alertname
        cooldown_seconds = ACTION_COOLDOWNS_SECONDS.get(action, 0)

        last = get_alert_last_execution(alert_key)
        if last and cooldown_seconds > 0:
            try:
                last_dt = _parse_ts(last)
                elapsed = (datetime.now(timezone.utc) - last_dt).total_seconds()
                if elapsed < cooldown_seconds:
                    return {
                        "decision": "cooldown",
                        "reason": "action recently executed",
                        "alert_key": alert_key,
                        "action": action,
                    }
            except Exception:
                pass

        return {
            "decision": "execute",
            "action": action,
            "payload": {},
            "alert_key": alert_key,
            "reason": "matched rule: BackupMissing firing -> run_backup",
        }

    return {
        "decision": "ignore",
        "reason": "no matching action rule",
    }
