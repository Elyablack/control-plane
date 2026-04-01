from __future__ import annotations

import json
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

from .config import DEFAULT_TASK_PRIORITY, HOST, PORT, TASK_PRIORITY_BY_SEVERITY
from .events import normalize_alertmanager_payload
from .executor import execute_action, now_utc
from .rule_loader import load_rules
from .rules import decide_alert_action
from .state import (
    create_decision,
    create_task,
    get_decision,
    get_run,
    get_task,
    init_db,
    list_decisions,
    list_runs,
    list_tasks,
)
from .worker import executor_worker_loop, notify_worker_loop

LOADED_RULES: list[dict[str, Any]] = []


def _priority_for_severity(severity: str) -> int:
    return TASK_PRIORITY_BY_SEVERITY.get(severity.lower(), DEFAULT_TASK_PRIORITY)


class ActionRunnerHandler(BaseHTTPRequestHandler):
    server_version = "action-runner/3.0"

    def _json_response(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

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

        if path == "/runs":
            self._json_response(HTTPStatus.OK, {"runs": list_runs()})
            return

        if path == "/decisions":
            self._json_response(HTTPStatus.OK, {"decisions": list_decisions()})
            return

        if path == "/tasks":
            self._json_response(HTTPStatus.OK, {"tasks": list_tasks()})
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

        if path == "/events/alertmanager":
            try:
                data = self._read_json()
                alerts = normalize_alertmanager_payload(data)
                decisions: list[dict[str, Any]] = []

                for alert in alerts:
                    decision = decide_alert_action(alert, LOADED_RULES)

                    base = {
                        "alertname": alert["alertname"],
                        "status": alert["status"],
                        "severity": alert["severity"],
                        "instance": alert["instance"],
                        "job": alert["job"],
                        "summary": alert["summary"],
                        "fingerprint": alert["fingerprint"],
                        "decision": decision["decision"],
                        "reason": decision["reason"],
                        "rule_name": decision.get("rule_name"),
                    }

                    action_name: str | None = decision.get("action")
                    decision_id = create_decision(
                        source="alertmanager",
                        alertname=alert["alertname"],
                        fingerprint=alert["fingerprint"],
                        severity=alert["severity"],
                        instance=alert["instance"],
                        job=alert["job"],
                        status=alert["status"],
                        summary=alert["summary"],
                        decision=decision["decision"],
                        reason=decision["reason"],
                        action=action_name if action_name else ("chain" if decision["decision"] == "execute_chain" else None),
                        run_id=None,
                        created_at=now_utc(),
                    )

                    base["decision_id"] = decision_id
                    task_priority = _priority_for_severity(alert["severity"])

                    if decision["decision"] == "execute":
                        task_payload = {
                            "action": decision["action"],
                            "payload": decision["payload"],
                            "alert_key": decision.get("alert_key"),
                        }
                        task_id = create_task(
                            decision_id=decision_id,
                            task_type="action",
                            payload=json.dumps(task_payload, ensure_ascii=False, sort_keys=True),
                            priority=task_priority,
                            created_at=now_utc(),
                        )
                        base["task_id"] = task_id

                    elif decision["decision"] == "execute_chain":
                        chain_context = {
                            "alertname": alert["alertname"],
                            "alert_status": alert["status"],
                            "severity": alert["severity"],
                            "instance": alert["instance"],
                            "job": alert["job"],
                            "summary": alert["summary"],
                            "fingerprint": alert["fingerprint"],
                            "rule_name": decision.get("rule_name") or "",
                        }

                        task_payload = {
                            "steps": decision["steps"],
                            "chain_context": chain_context,
                            "alert_key": decision.get("alert_key"),
                        }

                        task_id = create_task(
                            decision_id=decision_id,
                            task_type="chain",
                            payload=json.dumps(task_payload, ensure_ascii=False, sort_keys=True),
                            priority=task_priority,
                            created_at=now_utc(),
                        )
                        base["task_id"] = task_id
                        base["steps"] = decision["steps"]

                    decisions.append(base)

                self._json_response(
                    HTTPStatus.OK,
                    {
                        "status": "accepted",
                        "alerts_received": len(alerts),
                        "decisions": decisions,
                    },
                )
                return
            except Exception as exc:
                self._json_response(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return

        self._json_response(HTTPStatus.NOT_FOUND, {"error": "not found"})

    def log_message(self, format: str, *args: Any) -> None:
        return


def main() -> None:
    global LOADED_RULES
    init_db()
    LOADED_RULES = load_rules()

    executor_thread = threading.Thread(
        target=executor_worker_loop,
        name="executor-worker",
        daemon=True,
    )
    executor_thread.start()

    notify_thread = threading.Thread(
        target=notify_worker_loop,
        name="notify-worker",
        daemon=True,
    )
    notify_thread.start()

    server = ThreadingHTTPServer((HOST, PORT), ActionRunnerHandler)
    server.serve_forever()


if __name__ == "__main__":
    main()
