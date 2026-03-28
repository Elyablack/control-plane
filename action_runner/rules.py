from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from .state import get_alert_last_execution


COOLDOWN = timedelta(hours=1)


def _parse_ts(ts: str) -> datetime:
    return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S UTC").replace(tzinfo=timezone.utc)


def decide_alert_action(alert: dict[str, Any]) -> dict[str, Any]:
    alertname = str(alert.get("alertname", "")).strip()
    status = str(alert.get("status", "")).strip().lower()
    fingerprint = str(alert.get("fingerprint", "")).strip()

    if alertname == "BackupMissing" and status == "firing":
        alert_key = fingerprint or alertname

        last = get_alert_last_execution(alert_key)
        if last:
            try:
                last_dt = _parse_ts(last)
                if datetime.now(timezone.utc) - last_dt < COOLDOWN:
                    return {
                        "decision": "cooldown",
                        "reason": "action recently executed",
                        "alert_key": alert_key,
                    }
            except Exception:
                pass

        return {
            "decision": "execute",
            "action": "run_backup",
            "payload": {},
            "alert_key": alert_key,
            "reason": "matched rule: BackupMissing firing -> run_backup",
        }

    return {
        "decision": "ignore",
        "reason": "no matching action rule",
    }
