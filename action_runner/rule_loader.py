from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .config import ALLOWED_ACTIONS, RULES_PATH


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _normalize_step_when(rule_name: str, step_index: int, raw_when: Any) -> dict[str, Any] | None:
    if raw_when is None:
        return None

    if not isinstance(raw_when, dict):
        raise ValueError(f"rule '{rule_name}' step #{step_index} when must be an object")

    normalized_when: dict[str, Any] = {}

    if "analysis_level_in" in raw_when:
        levels = raw_when.get("analysis_level_in")
        if not isinstance(levels, list) or not levels:
            raise ValueError(
                f"rule '{rule_name}' step #{step_index} when.analysis_level_in must be a non-empty list"
            )

        normalized_levels = [str(v).strip() for v in levels if str(v).strip()]
        if not normalized_levels:
            raise ValueError(
                f"rule '{rule_name}' step #{step_index} when.analysis_level_in must contain values"
            )

        normalized_when["analysis_level_in"] = normalized_levels

    unknown_keys = set(raw_when) - {"analysis_level_in"}
    if unknown_keys:
        unknown = ", ".join(sorted(unknown_keys))
        raise ValueError(f"rule '{rule_name}' step #{step_index} has unsupported when keys: {unknown}")

    return normalized_when or None


def load_rules(path: Path | None = None) -> list[dict[str, Any]]:
    rules_path = path or RULES_PATH

    if not rules_path.exists():
        raise FileNotFoundError(f"rules file not found: {rules_path}")

    with rules_path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    if not isinstance(raw, dict):
        raise ValueError("rules file must contain a top-level object")

    rules = raw.get("rules", [])
    if not isinstance(rules, list):
        raise ValueError("rules must be a list")

    validated: list[dict[str, Any]] = []

    for idx, rule in enumerate(rules, start=1):
        if not isinstance(rule, dict):
            raise ValueError(f"rule #{idx} must be an object")

        name = str(rule.get("name", "")).strip()
        if not name:
            raise ValueError(f"rule #{idx} is missing 'name'")

        enabled = bool(rule.get("enabled", True))
        match = _as_dict(rule.get("match"))
        action = _as_dict(rule.get("action"))

        if not match:
            raise ValueError(f"rule '{name}' must define non-empty 'match'")

        action_type = str(action.get("type", "")).strip()
        if action_type not in {"execute", "ignore", "chain"}:
            raise ValueError(f"rule '{name}' has unsupported action.type '{action_type}'")

        normalized_action: dict[str, Any] = {"type": action_type}

        if action_type == "execute":
            action_name = str(action.get("name", "")).strip()
            if not action_name:
                raise ValueError(f"rule '{name}' must define action.name for execute type")
            if action_name not in ALLOWED_ACTIONS:
                raise ValueError(f"rule '{name}' references unsupported action '{action_name}'")

            payload = action.get("payload", {})
            if not isinstance(payload, dict):
                raise ValueError(f"rule '{name}' action.payload must be an object")

            normalized_action["name"] = action_name
            normalized_action["payload"] = payload

        elif action_type == "chain":
            raw_steps = _as_list(action.get("steps"))
            if not raw_steps:
                raise ValueError(f"rule '{name}' chain must define at least one step")

            steps: list[dict[str, Any]] = []
            for step_index, raw_step in enumerate(raw_steps, start=1):
                if not isinstance(raw_step, dict):
                    raise ValueError(f"rule '{name}' step #{step_index} must be an object")

                step_name = str(raw_step.get("name", "")).strip()
                if not step_name:
                    raise ValueError(f"rule '{name}' step #{step_index} is missing name")
                if step_name not in ALLOWED_ACTIONS:
                    raise ValueError(f"rule '{name}' step #{step_index} references unsupported action '{step_name}'")

                step_payload = raw_step.get("payload", {})
                if not isinstance(step_payload, dict):
                    raise ValueError(f"rule '{name}' step #{step_index} payload must be an object")

                retries = int(raw_step.get("retries", 0))
                if retries < 0:
                    raise ValueError(f"rule '{name}' step #{step_index} retries must be >= 0")

                retry_delay_seconds = int(raw_step.get("retry_delay_seconds", 0))
                if retry_delay_seconds < 0:
                    raise ValueError(f"rule '{name}' step #{step_index} retry_delay_seconds must be >= 0")

                normalized_when = _normalize_step_when(name, step_index, raw_step.get("when"))

                step_data = {
                    "name": step_name,
                    "payload": step_payload,
                    "retries": retries,
                    "retry_delay_seconds": retry_delay_seconds,
                }

                if normalized_when is not None:
                    step_data["when"] = normalized_when

                steps.append(step_data)

            normalized_action["steps"] = steps

        cooldown_seconds = int(rule.get("cooldown_seconds", 0))
        if cooldown_seconds < 0:
            raise ValueError(f"rule '{name}' cooldown_seconds must be >= 0")

        validated.append(
            {
                "name": name,
                "enabled": enabled,
                "match": {str(k): str(v) for k, v in match.items()},
                "action": normalized_action,
                "cooldown_seconds": cooldown_seconds,
            }
        )

    return validated
