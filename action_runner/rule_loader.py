from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .config import ALLOWED_ACTIONS, RULES_PATH


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


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
        if action_type not in {"execute", "ignore"}:
            raise ValueError(f"rule '{name}' has unsupported action.type '{action_type}'")

        action_name = None
        action_payload: dict[str, Any] = {}

        if action_type == "execute":
            action_name = str(action.get("name", "")).strip()
            if not action_name:
                raise ValueError(f"rule '{name}' must define action.name for execute type")
            if action_name not in ALLOWED_ACTIONS:
                raise ValueError(f"rule '{name}' references unsupported action '{action_name}'")

            raw_payload = action.get("payload", {})
            if not isinstance(raw_payload, dict):
                raise ValueError(f"rule '{name}' action.payload must be an object")
            action_payload = raw_payload

        cooldown_seconds = int(rule.get("cooldown_seconds", 0))
        if cooldown_seconds < 0:
            raise ValueError(f"rule '{name}' cooldown_seconds must be >= 0")

        validated.append(
            {
                "name": name,
                "enabled": enabled,
                "match": {str(k): str(v) for k, v in match.items()},
                "action": {
                    "type": action_type,
                    "name": action_name,
                    "payload": action_payload,
                },
                "cooldown_seconds": cooldown_seconds,
            }
        )

    return validated
