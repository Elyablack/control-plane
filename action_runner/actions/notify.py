from __future__ import annotations

import json
import subprocess
import urllib.error
import urllib.request
from typing import Any

from ..config import TG_RELAY_TIMEOUT_SECONDS, TG_RELAY_URL
from .types import ActionResult


def _as_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def _build_alertmanager_like_payload(payload: dict[str, Any]) -> dict[str, Any]:
    message = _as_str(payload.get("message"), "Notification from action-runner")
    event = _as_str(payload.get("event"), "action_runner_event")
    source = _as_str(payload.get("source"), "action-runner")
    severity = _as_str(payload.get("severity"), "info")
    status = _as_str(payload.get("status"), "firing")
    description = _as_str(payload.get("description"), message)

    alert = {
        "status": status,
        "labels": {
            "alertname": event or "ActionRunnerNotification",
            "severity": severity or "info",
            "service": source or "action-runner",
            "job": "action-runner",
            "instance": "vps",
        },
        "annotations": {
            "summary": message,
            "description": description,
        },
    }

    return {
        "receiver": "action-runner",
        "status": status,
        "alerts": [alert],
        "groupLabels": {
            "alertname": alert["labels"]["alertname"],
        },
        "commonLabels": {
            "severity": alert["labels"]["severity"],
            "service": alert["labels"]["service"],
        },
        "commonAnnotations": {
            "summary": message,
        },
    }


def _build_message_payload(payload: dict[str, Any]) -> dict[str, Any]:
    message = _as_str(payload.get("message"), "Notification from action-runner")
    description = _as_str(payload.get("description"))
    event = _as_str(payload.get("event"), "action_runner_event")
    source = _as_str(payload.get("source"), "action-runner")
    severity = _as_str(payload.get("severity"), "info")
    status = _as_str(payload.get("status"), "firing")

    lines = [message]
    if description:
        lines.append("")
        lines.append(description)

    text = "\n".join(lines).strip()

    return {
        "receiver": "action-runner",
        "status": status,
        "alerts": [
            {
                "status": status,
                "labels": {
                    "alertname": event,
                    "severity": severity,
                    "service": source,
                    "job": "control-plane",
                    "instance": "vps",
                },
                "annotations": {
                    "summary": message,
                    "description": text,
                },
            }
        ],
        "groupLabels": {
            "alertname": event,
        },
        "commonLabels": {
            "severity": severity,
            "service": source,
        },
        "commonAnnotations": {
            "summary": message,
        },
    }


def notify_tg(payload: dict[str, Any]) -> ActionResult:
    format_name = _as_str(payload.get("format"), "message").lower()

    if format_name == "alertmanager":
        relay_payload = _build_alertmanager_like_payload(payload)
    elif format_name == "message":
        relay_payload = _build_message_payload(payload)
    else:
        return ActionResult(
            status="failed",
            exit_code=1,
            stdout="",
            stderr="",
            error=f"unsupported notify_tg format: {format_name}",
        )

    body = json.dumps(relay_payload, ensure_ascii=False).encode("utf-8")

    req = urllib.request.Request(
        TG_RELAY_URL,
        data=body,
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": "control-plane/1.0",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=TG_RELAY_TIMEOUT_SECONDS) as resp:
            response_body = resp.read().decode("utf-8", errors="replace")
            return ActionResult(
                status="success",
                exit_code=0,
                stdout=response_body,
                stderr="",
                error=None,
            )
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        return ActionResult(
            status="failed",
            exit_code=1,
            stdout="",
            stderr=f"tg-relay http error {exc.code}: {error_body}",
            error=f"tg-relay http error {exc.code}",
        )
    except Exception as exc:
        return ActionResult(
            status="failed",
            exit_code=1,
            stdout="",
            stderr=f"tg-relay request failed: {exc}",
            error=f"tg-relay request failed: {exc}",
        )
