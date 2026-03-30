from __future__ import annotations

import json
import subprocess
import urllib.error
import urllib.request
from typing import Any

from ..config import TG_RELAY_TIMEOUT_SECONDS, TG_RELAY_URL


def _build_alertmanager_like_payload(payload: dict[str, Any]) -> dict[str, Any]:
    message = str(payload.get("message", "Notification from action-runner")).strip()
    event = str(payload.get("event", "action_runner_event")).strip()
    source = str(payload.get("source", "action-runner")).strip()
    severity = str(payload.get("severity", "info")).strip()
    status = str(payload.get("status", "firing")).strip()

    description = str(payload.get("description", "")).strip()

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
            "description": description or message,
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


def notify_tg(payload: dict[str, Any]) -> subprocess.CompletedProcess[str]:
    relay_payload = _build_alertmanager_like_payload(payload)
    body = json.dumps(relay_payload, ensure_ascii=False).encode("utf-8")

    req = urllib.request.Request(
        TG_RELAY_URL,
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=TG_RELAY_TIMEOUT_SECONDS) as resp:
            response_body = resp.read().decode("utf-8", errors="replace")
            return subprocess.CompletedProcess(
                args=["notify_tg"],
                returncode=0,
                stdout=response_body,
                stderr="",
            )
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        return subprocess.CompletedProcess(
            args=["notify_tg"],
            returncode=1,
            stdout="",
            stderr=f"tg-relay http error {exc.code}: {error_body}",
        )
    except Exception as exc:
        return subprocess.CompletedProcess(
            args=["notify_tg"],
            returncode=1,
            stdout="",
            stderr=f"tg-relay request failed: {exc}",
        )
