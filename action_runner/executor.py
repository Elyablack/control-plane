from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from typing import Any

from .actions import ACTION_HANDLERS
from .config import ALLOWED_ACTIONS
from .state import (
    acquire_action_lock,
    create_run,
    finish_run,
    get_action_lock,
    release_action_lock,
)


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def execute_action(action: str, payload: dict[str, Any], *, trigger_type: str) -> dict[str, Any]:
    if action not in ALLOWED_ACTIONS:
        raise ValueError(f"action '{action}' is not allowed")

    handler = ACTION_HANDLERS.get(action)
    if handler is None:
        raise ValueError(f"no handler registered for action '{action}'")

    started_at = now_utc()

    existing_lock = get_action_lock(action)
    if existing_lock is not None:
        return {
            "run_id": None,
            "action": action,
            "status": "blocked",
            "reason": "action is already running",
            "locked_by_run_id": existing_lock["run_id"],
            "acquired_at": existing_lock["acquired_at"],
        }

    run_id = create_run(
        action=action,
        trigger_type=trigger_type,
        trigger_payload=json.dumps(payload, ensure_ascii=False, sort_keys=True),
        started_at=started_at,
    )

    lock_acquired = acquire_action_lock(action, run_id, started_at)
    if not lock_acquired:
        finish_run(
            run_id,
            status="blocked",
            finished_at=now_utc(),
            exit_code=None,
            stdout="",
            stderr="",
            error="action lock could not be acquired",
        )
        return {
            "run_id": run_id,
            "action": action,
            "status": "blocked",
            "reason": "action lock could not be acquired",
            "detail_url": f"/runs/{run_id}",
        }

    try:
        result = handler(payload)

        finished_at = now_utc()
        status = "success" if result.returncode == 0 else "failed"
        error = None if result.returncode == 0 else f"command exited with code {result.returncode}"

        finish_run(
            run_id,
            status=status,
            finished_at=finished_at,
            exit_code=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            error=error,
        )

        return {
            "run_id": run_id,
            "action": action,
            "status": status,
            "started_at": started_at,
            "finished_at": finished_at,
            "exit_code": result.returncode,
            "detail_url": f"/runs/{run_id}",
        }
    finally:
        release_action_lock(action)


_TEMPLATE_RE = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)(\|upper|\|lower)?\s*\}\}")


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _render_string(template: str, context: dict[str, Any]) -> str:
    def repl(match: re.Match[str]) -> str:
        key = match.group(1)
        transform = match.group(2)
        value = _stringify(context.get(key, ""))

        if transform == "|upper":
            return value.upper()
        if transform == "|lower":
            return value.lower()
        return value

    return _TEMPLATE_RE.sub(repl, template)


def _render_payload(value: Any, context: dict[str, Any]) -> Any:
    if isinstance(value, str):
        return _render_string(value, context)
    if isinstance(value, dict):
        return {k: _render_payload(v, context) for k, v in value.items()}
    if isinstance(value, list):
        return [_render_payload(v, context) for v in value]
    return value


def execute_chain(
    steps: list[dict[str, Any]],
    *,
    trigger_type: str,
    chain_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not steps:
        raise ValueError("chain must contain at least one step")

    context = dict(chain_context or {})
    chain_started_at = now_utc()
    step_results: list[dict[str, Any]] = []
    first_run_id: int | None = None
    last_run_id: int | None = None
    chain_status = "success"

    for index, step in enumerate(steps, start=1):
        action_name = str(step.get("name", "")).strip()
        raw_payload = step.get("payload", {})
        retries = int(step.get("retries", 0))
        retry_delay_seconds = int(step.get("retry_delay_seconds", 0))

        if not isinstance(raw_payload, dict):
            raise ValueError(f"chain step #{index} payload must be an object")

        context.update(
            {
                "step": index,
                "step_name": action_name,
                "step_count": len(step_results),
                "chain_status": chain_status,
                "first_run_id": first_run_id or "",
                "last_run_id": last_run_id or "",
            }
        )

        rendered_payload = _render_payload(raw_payload, context)

        attempt_results: list[dict[str, Any]] = []
        final_result: dict[str, Any] | None = None

        for attempt in range(1, retries + 2):
            result = execute_action(action_name, rendered_payload, trigger_type=trigger_type)
            attempt_results.append(
                {
                    "attempt": attempt,
                    "result": result,
                }
            )
            final_result = result

            run_id = result.get("run_id")
            if isinstance(run_id, int):
                if first_run_id is None:
                    first_run_id = run_id
                last_run_id = run_id

            if result.get("status") == "success":
                break

            if attempt <= retries and retry_delay_seconds > 0:
                time.sleep(retry_delay_seconds)

        step_entry = {
            "step": index,
            "action": action_name,
            "rendered_payload": rendered_payload,
            "attempts": attempt_results,
            "result": final_result,
        }
        step_results.append(step_entry)

        context.update(
            {
                "step_count": len(step_results),
                "first_run_id": first_run_id or "",
                "last_run_id": last_run_id or "",
                "last_action": action_name,
                "last_step_status": final_result.get("status") if final_result else "failed",
            }
        )

        if final_result is None or final_result.get("status") != "success":
            chain_status = "failed"
            return {
                "status": "failed",
                "started_at": chain_started_at,
                "finished_at": now_utc(),
                "first_run_id": first_run_id,
                "last_run_id": last_run_id,
                "step_results": step_results,
            }

    chain_status = "success"
    return {
        "status": chain_status,
        "started_at": chain_started_at,
        "finished_at": now_utc(),
        "first_run_id": first_run_id,
        "last_run_id": last_run_id,
        "step_results": step_results,
    }
