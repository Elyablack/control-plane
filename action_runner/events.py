from __future__ import annotations

from typing import Any


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _pick_str(*values: Any, default: str = "") -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return default


def normalize_alertmanager_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    alerts = payload.get("alerts", [])
    if not isinstance(alerts, list):
        return []

    normalized: list[dict[str, Any]] = []

    for alert in alerts:
        if not isinstance(alert, dict):
            continue

        labels = _as_dict(alert.get("labels"))
        annotations = _as_dict(alert.get("annotations"))

        normalized.append(
            {
                "status": _pick_str(alert.get("status")).lower(),
                "alertname": _pick_str(labels.get("alertname")),
                "severity": _pick_str(labels.get("severity")),
                "instance": _pick_str(labels.get("instance")),
                "job": _pick_str(labels.get("job")),
                "summary": _pick_str(annotations.get("summary")),
                "description": _pick_str(annotations.get("description")),
                "labels": labels,
                "annotations": annotations,
                "raw": alert,
            }
        )

    return normalized
