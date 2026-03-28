from __future__ import annotations

from typing import Any, Optional


def match_alertmanager_action(payload: dict[str, Any]) -> Optional[dict[str, Any]]:
    alerts = payload.get("alerts", [])
    if not isinstance(alerts, list):
        return None

    for alert in alerts:
        if not isinstance(alert, dict):
            continue

        status = str(alert.get("status", "")).lower()
        labels = alert.get("labels", {})
        if not isinstance(labels, dict):
            labels = {}

        alertname = str(labels.get("alertname", ""))

        if alertname == "BackupMissing" and status == "firing":
            return {
                "action": "run_backup",
                "payload": {},
                "reason": "matched BackupMissing firing rule",
                "matched_alertname": alertname,
                "matched_status": status,
            }

    return None
