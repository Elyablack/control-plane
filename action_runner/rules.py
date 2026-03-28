from __future__ import annotations

from typing import Any


def decide_alert_action(alert: dict[str, Any]) -> dict[str, Any]:
    alertname = str(alert.get("alertname", "")).strip()
    status = str(alert.get("status", "")).strip().lower()

    if alertname == "BackupMissing" and status == "firing":
        return {
            "decision": "execute",
            "action": "run_backup",
            "payload": {},
            "reason": "matched rule: BackupMissing firing -> run_backup",
        }

    return {
        "decision": "ignore",
        "reason": "no matching action rule",
    }
