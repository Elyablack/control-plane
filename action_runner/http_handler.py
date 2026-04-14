from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from typing import Any
from urllib.parse import urlparse

from .events import normalize_alertmanager_payload
from .executor import execute_action, now_utc
from .mac_host_audit import save_mac_host_audit_snapshot
from .metrics import PROMETHEUS_CONTENT_TYPE, render_metrics
from .runtime import LOADED_RULES
from .signal_service import process_signals
from .state import (
    finish_task,
    get_decision,
    get_next_task,
    get_run,
    get_task,
    list_decisions,
    list_runs,
    list_tasks,
    start_task,
)
from .task_service import queue_notify_task


class ActionRunnerHandler(BaseHTTPRequestHandler):
    server_version = "action-runner/4.1"

    def _json_response(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _text_response(self, status: int, body: str, content_type: str) -> None:
        payload = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _read_json(self) -> dict[str, Any]:
        content_length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(content_length) if content_length > 0 else b"{}"
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("JSON body must be an object")
        return data

    def do_GET(self) -> None:
        path = urlparse(self.path).path

        if path == "/healthz":
            self._json_response(
                HTTPStatus.OK,
                {
                    "status": "ok",
                    "service": "action-runner",
                    "rules_loaded": len(LOADED_RULES),
                },
            )
            return

        if path == "/metrics":
            try:
                self._text_response(
                    HTTPStatus.OK,
                    render_metrics(),
                    PROMETHEUS_CONTENT_TYPE,
                )
                return
            except Exception as exc:
                self._json_response(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
                return

        if path == "/runs":
            self._json_response(HTTPStatus.OK, {"runs": list_runs()})
            return

        if path == "/decisions":
            self._json_response(HTTPStatus.OK, {"decisions": list_decisions()})
            return

        if path == "/tasks":
            self._json_response(HTTPStatus.OK, {"tasks": list_tasks()})
            return

        if path == "/tasks/mac/next":
            try:
                task = get_next_task(["mac_action"])
                if task is None:
                    self._json_response(HTTPStatus.OK, {"task": None})
                    return

                start_task(task["id"], now_utc())
                self._json_response(HTTPStatus.OK, {"task": task})
                return

            except Exception as exc:
                self._json_response(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return

        if path.startswith("/runs/"):
            raw_id = path.removeprefix("/runs/").strip()
            if not raw_id.isdigit():
                self._json_response(HTTPStatus.BAD_REQUEST, {"error": "run id must be an integer"})
                return

            run = get_run(int(raw_id))
            if run is None:
                self._json_response(HTTPStatus.NOT_FOUND, {"error": "run not found"})
                return

            self._json_response(HTTPStatus.OK, run)
            return

        if path.startswith("/decisions/"):
            raw_id = path.removeprefix("/decisions/").strip()
            if not raw_id.isdigit():
                self._json_response(HTTPStatus.BAD_REQUEST, {"error": "decision id must be an integer"})
                return

            decision = get_decision(int(raw_id))
            if decision is None:
                self._json_response(HTTPStatus.NOT_FOUND, {"error": "decision not found"})
                return

            self._json_response(HTTPStatus.OK, decision)
            return

        if path.startswith("/tasks/"):
            raw_id = path.removeprefix("/tasks/").strip()
            if not raw_id.isdigit():
                self._json_response(HTTPStatus.BAD_REQUEST, {"error": "task id must be an integer"})
                return

            task = get_task(int(raw_id))
            if task is None:
                self._json_response(HTTPStatus.NOT_FOUND, {"error": "task not found"})
                return

            self._json_response(HTTPStatus.OK, task)
            return

        self._json_response(HTTPStatus.NOT_FOUND, {"error": "not found"})

    def do_POST(self) -> None:
        path = urlparse(self.path).path

        if path == "/actions/run":
            try:
                data = self._read_json()
                action = data.get("action")
                payload = data.get("payload", {})

                if not isinstance(action, str) or not action.strip():
                    raise ValueError("field 'action' is required")
                if not isinstance(payload, dict):
                    raise ValueError("field 'payload' must be an object")

                result = execute_action(action.strip(), payload, trigger_type="manual")
                self._json_response(HTTPStatus.OK, result)
                return
            except Exception as exc:
                self._json_response(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return

        if path == "/tasks/mac/complete":
            try:
                data = self._read_json()

                task_id = int(data["task_id"])
                status = str(data.get("status", "success")).strip().lower()
                result = data.get("result", {})
                if not isinstance(result, dict):
                    raise ValueError("field 'result' must be an object")
                if status not in {"success", "skipped", "failed"}:
                    raise ValueError("field 'status' must be one of: success, skipped, failed")

                current_task = get_task(task_id)
                if current_task is None:
                    self._json_response(HTTPStatus.NOT_FOUND, {"error": "task not found"})
                    return

                finish_task(
                    task_id,
                    status=status,
                    finished_at=now_utc(),
                    result_json=json.dumps(result, ensure_ascii=False, sort_keys=True),
                    error=result.get("error") if status == "failed" and isinstance(result.get("error"), str) else None,
                )

                notify_task_id: int | None = None

                if current_task["task_type"] == "mac_action" and status == "failed":
                    raw_payload = current_task.get("payload") or "{}"
                    try:
                        task_payload = json.loads(raw_payload)
                    except Exception:
                        task_payload = {}

                    instance = str(task_payload.get("instance", "unknown")).strip() or "unknown"
                    action = str(task_payload.get("action", "unknown")).strip() or "unknown"
                    target = str(result.get("target", task_payload.get("target", ""))).strip()
                    error_text = str(result.get("error", "unknown remediation failure")).strip()

                    description_lines = [
                        "Remote mac remediation failed",
                        "",
                        f"task_id: {task_id}",
                        f"instance: {instance}",
                        f"action: {action}",
                    ]
                    if target:
                        description_lines.append(f"target: {target}")
                    description_lines.append(f"error: {error_text}")

                    notify_task_id = queue_notify_task(
                        decision_id=current_task.get("decision_id"),
                        severity="critical",
                        message=f"[MAC][REMEDIATION FAILED] {action} on {instance}",
                        description="\n".join(description_lines),
                        event="mac_remediation_failed",
                    )

                response = {
                    "status": "ok",
                    "task_status": status,
                }
                if notify_task_id is not None:
                    response["notify_task_id"] = notify_task_id

                self._json_response(HTTPStatus.OK, response)
                return

            except Exception as exc:
                self._json_response(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return

        if path == "/events/mac-host-audit":
            try:
                data = self._read_json()
                log_path = save_mac_host_audit_snapshot(data)
                self._json_response(
                    HTTPStatus.OK,
                    {
                        "status": "ok",
                        "log_path": log_path,
                    },
                )
                return
            except Exception as exc:
                self._json_response(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return

        if path == "/events/alertmanager":
            try:
                data = self._read_json()
                alerts = normalize_alertmanager_payload(data)
                result = process_signals(alerts, source="alertmanager")
                self._json_response(HTTPStatus.OK, result)
                return
            except Exception as exc:
                self._json_response(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return

        self._json_response(HTTPStatus.NOT_FOUND, {"error": "not found"})

    def log_message(self, format: str, *args: Any) -> None:
        return

