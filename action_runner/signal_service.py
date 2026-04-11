from __future__ import annotations

import json
from typing import Any

from .executor import now_utc
from .rules import decide_alert_action
from .runtime import LOADED_RULES
from .state import create_decision, create_task
from .task_service import priority_for_severity


def _extract_signal_context(signal: dict[str, Any]) -> dict[str, Any]:
    context = signal.get("context")
    if isinstance(context, dict):
        return dict(context)
    return {}


def process_single_signal(signal: dict[str, Any], *, source: str) -> dict[str, Any]:
    decision = decide_alert_action(signal, LOADED_RULES)
    signal_context = _extract_signal_context(signal)

    base = {
        "alertname": signal["alertname"],
        "status": signal["status"],
        "severity": signal["severity"],
        "instance": signal["instance"],
        "job": signal["job"],
        "summary": signal["summary"],
        "description": signal.get("description", ""),
        "fingerprint": signal["fingerprint"],
        "decision": decision["decision"],
        "reason": decision["reason"],
        "rule_name": decision.get("rule_name"),
        "context": signal_context,
    }
    base.update(signal_context)

    action_name: str | None = decision.get("action")
    decision_id = create_decision(
        source=source,
        alertname=signal["alertname"],
        fingerprint=signal["fingerprint"],
        severity=signal["severity"],
        instance=signal["instance"],
        job=signal["job"],
        status=signal["status"],
        summary=signal["summary"],
        decision=decision["decision"],
        reason=decision["reason"],
        action=action_name if action_name else ("chain" if decision["decision"] == "execute_chain" else None),
        run_id=None,
        created_at=now_utc(),
    )

    base["decision_id"] = decision_id
    task_priority = priority_for_severity(signal["severity"])

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
            "alertname": signal["alertname"],
            "alert_status": signal["status"],
            "severity": signal["severity"],
            "instance": signal["instance"],
            "job": signal["job"],
            "summary": signal["summary"],
            "description": signal.get("description", ""),
            "fingerprint": signal["fingerprint"],
            "rule_name": decision.get("rule_name") or "",
            "context": signal_context,
        }
        chain_context.update(signal_context)

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

    return base


def process_signals(
    signals: list[dict[str, Any]],
    *,
    source: str,
) -> dict[str, Any]:
    decisions: list[dict[str, Any]] = []

    for signal in signals:
        decisions.append(process_single_signal(signal, source=source))

    return {
        "status": "accepted",
        "alerts_received": len(signals),
        "decisions": decisions,
    }
