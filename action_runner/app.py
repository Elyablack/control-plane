from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

from .config import HOST, PORT
from .executor import execute_action
from .state import get_run, init_db, list_runs


class ActionRunnerHandler(BaseHTTPRequestHandler):
    server_version = "action-runner/0.2"

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
                {"status": "ok", "service": "action-runner"},
            )
            return

        if path == "/runs":
            self._json_response(
                HTTPStatus.OK,
                {"runs": list_runs()},
            )
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

        self._json_response(
            HTTPStatus.NOT_FOUND,
            {"error": "not found"},
        )

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
                self._json_response(
                    HTTPStatus.BAD_REQUEST,
                    {"error": str(exc)},
                )
                return

        self._json_response(
            HTTPStatus.NOT_FOUND,
            {"error": "not found"},
        )

    def log_message(self, format: str, *args: Any) -> None:
        return


def main() -> None:
    init_db()
    server = ThreadingHTTPServer((HOST, PORT), ActionRunnerHandler)
    server.serve_forever()


if __name__ == "__main__":
    main()
