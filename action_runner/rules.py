from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .state import get_alert_last_execution


def _parse_ts(ts: str) -> datetime:
    return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S UTC").replace(tzinfo=timezone.utc)


def _matches(alert: dict[str, Any], match: dict[str, str]) -> bool:
    for key, expected in match.items():
        actual = str(alert.get(key, "")).strip()
        if actual != expected:
            return False
    return True


def decide_alert_action(alert: dict[str, Any], rules: list[dict[str, Any]]) -> dict[str, Any]:
    fingerprint = str(alert.get("fingerprint", "")).strip()
    fallback_key = str(alert.get("alertname", "")).strip() or "unknown-alert"

    for rule in rules:
        if not rule.get("enabled", True):
            continue

        if not _matches(alert, rule["match"]):
            continue

        action_block = rule["action"]
        action_type = action_block["type"]
        action_name = action_block.get("name")
        cooldown_seconds = int(rule.get("cooldown_seconds", 0))
        alert_key = f"{rule['name']}:{fingerprint or fallback_key}"

        if action_type == "ignore":
            return {
                "decision": "ignore",
                "reason": f"matched ignore rule: {rule['name']}",
                "rule_name": rule["name"],
                "alert_key": alert_key,
            }

        if action_type == "execute":
            last = get_alert_last_execution(alert_key)
            if last and cooldown_seconds > 0:
                try:
                    last_dt = _parse_ts(last)
                    elapsed = (datetime.now(timezone.utc) - last_dt).total_seconds()
                    if elapsed < cooldown_seconds:
                        return {
                            "decision": "cooldown",
                            "reason": f"matched rule '{rule['name']}' but action recently executed",
                            "rule_name": rule["name"],
                            "alert_key": alert_key,
                            "action": action_name,
                            "cooldown_seconds": cooldown_seconds,
                        }
                except Exception:
                    pass

            return {
                "decision": "execute",
                "reason": f"matched execute rule: {rule['name']}",
                "rule_name": rule["name"],
                "alert_key": alert_key,
                "action": action_name,
                "payload": action_block.get("payload", {}),
                "cooldown_seconds": cooldown_seconds,
            }

    return {
        "decision": "ignore",
        "reason": "no matching action rule",
        "rule_name": None,
        "alert_key": fingerprint or fallback_key,
    }
