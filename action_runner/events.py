from __future__ import annotations

import hashlib
import json
from typing import Any


_CONTEXT_KEYS_FROM_ANNOTATIONS = (
    "top_app",
    "top_rss_mb",
    "swap_used_mb",
    "memory_free_percent",
    "uptime_days",
    "disk_used_percent",
    "suggested_action",
    "reason_text",
    "timestamp_utc",
)


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


def _build_fingerprint(labels: dict[str, Any], explicit_fingerprint: Any) -> str:
    fp = _pick_str(explicit_fingerprint)
    if fp:
        return fp

    normalized = {str(k): str(v) for k, v in sorted(labels.items())}
    raw = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _extract_context(labels: dict[str, Any], annotations: dict[str, Any]) -> dict[str, Any]:
    context: dict[str, Any] = {}

    for key in _CONTEXT_KEYS_FROM_ANNOTATIONS:
        value = annotations.get(key)
        if value is None:
            value = labels.get(key)
        if value is None:
            continue

        text = str(value).strip()
        if text:
            context[key] = text

    return context


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
        context = _extract_context(labels, annotations)

        normalized.append(
            {
                "status": _pick_str(alert.get("status")).lower(),
                "alertname": _pick_str(labels.get("alertname")),
                "severity": _pick_str(labels.get("severity")),
                "instance": _pick_str(labels.get("instance")),
                "job": _pick_str(labels.get("job")),
                "summary": _pick_str(annotations.get("summary")),
                "description": _pick_str(annotations.get("description")),
                "fingerprint": _build_fingerprint(labels, alert.get("fingerprint")),
                "labels": labels,
                "annotations": annotations,
                "context": context,
                "raw": alert,
            }
        )

    return normalized
