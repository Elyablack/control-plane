from __future__ import annotations

import json
import subprocess
from typing import Any

from .logging_utils import log_line

PROTECTED_APPS = {
    "ChatGPT",
    "Terminal",
    "iTerm",
    "Cursor",
    "VSCode",
    "Obsidian",
    "Telegram",
    "Safari",
}

SAFE_SOFT_QUIT_TARGETS = {
    "Music",
    "Notes",
}

CANDIDATE_ORDER = [
    "Music",
    "Notes",
]


def _list_running_apps() -> set[str]:
    script = r'''
    tell application "System Events"
        set app_names to name of every application process whose background only is false
    end tell

    set {oldTID, AppleScript's text item delimiters} to {AppleScript's text item delimiters, linefeed}
    set output_text to app_names as text
    set AppleScript's text item delimiters to oldTID

    return output_text
    '''
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            check=True,
        )

        raw = result.stdout.strip()
        if not raw:
            log_line("mac remediation: running apps list is empty")
            return set()

        apps = {line.strip() for line in raw.splitlines() if line.strip()}
        log_line(f"mac remediation: running apps={sorted(apps)}")
        return apps

    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.strip() if exc.stderr else ""
        stdout = exc.stdout.strip() if exc.stdout else ""
        log_line(f"mac remediation: list running apps failed stdout={stdout} stderr={stderr}")
        return set()


def _select_allowlisted_candidate() -> str | None:
    running = _list_running_apps()
    if not running:
        log_line("mac remediation: no running apps visible")
        return None

    for name in CANDIDATE_ORDER:
        if name in running and name in SAFE_SOFT_QUIT_TARGETS and name not in PROTECTED_APPS:
            log_line(f"mac remediation: selected candidate={name}")
            return name

    log_line("mac remediation: no eligible allowlisted running app found")
    return None


def _soft_quit(target: str) -> tuple[bool, str, str]:
    try:
        result = subprocess.run(
            ["osascript", "-e", f'tell application "{target}" to quit'],
            capture_output=True,
            text=True,
            check=True,
        )
        return True, result.stdout.strip(), result.stderr.strip()
    except subprocess.CalledProcessError as exc:
        stdout = exc.stdout.strip() if exc.stdout else ""
        stderr = exc.stderr.strip() if exc.stderr else ""
        return False, stdout, stderr


def execute_mac_action(task: dict[str, Any]) -> dict[str, Any]:
    task_id = task.get("id")
    raw_payload = task.get("payload", "{}")

    try:
        payload = json.loads(raw_payload)
    except Exception as exc:
        return {
            "status": "failed",
            "task_id": task_id,
            "error": f"invalid task payload: {exc}",
        }

    action = str(payload.get("action", "")).strip()
    instance = str(payload.get("instance", "")).strip()

    log_line(f"mac remediation: task_id={task_id} action={action} instance={instance}")

    if action == "soft_quit_allowlisted_candidate":
        target = _select_allowlisted_candidate()
        if target is None:
            return {
                "status": "failed",
                "task_id": task_id,
                "action": action,
                "instance": instance,
                "error": "no eligible allowlisted running app found",
            }

        ok, stdout, stderr = _soft_quit(target)
        if ok:
            log_line(f"mac remediation: soft quit ok target={target}")
            return {
                "status": "success",
                "task_id": task_id,
                "action": action,
                "target": target,
                "instance": instance,
            }

        log_line(f"mac remediation: soft quit failed target={target} stdout={stdout} stderr={stderr}")
        return {
            "status": "failed",
            "task_id": task_id,
            "action": action,
            "target": target,
            "instance": instance,
            "stdout": stdout,
            "stderr": stderr,
            "error": f"soft quit failed for {target}",
        }

    if action == "soft_quit":
        target = str(payload.get("target", "")).strip()

        if target not in SAFE_SOFT_QUIT_TARGETS:
            return {
                "status": "failed",
                "task_id": task_id,
                "action": action,
                "target": target,
                "instance": instance,
                "error": f"target is not allowlisted: {target}",
            }

        if target in PROTECTED_APPS:
            return {
                "status": "failed",
                "task_id": task_id,
                "action": action,
                "target": target,
                "instance": instance,
                "error": f"target is protected: {target}",
            }

        ok, stdout, stderr = _soft_quit(target)
        if ok:
            log_line(f"mac remediation: soft quit ok target={target}")
            return {
                "status": "success",
                "task_id": task_id,
                "action": action,
                "target": target,
                "instance": instance,
            }

        log_line(f"mac remediation: soft quit failed target={target} stdout={stdout} stderr={stderr}")
        return {
            "status": "failed",
            "task_id": task_id,
            "action": action,
            "target": target,
            "instance": instance,
            "stdout": stdout,
            "stderr": stderr,
            "error": f"soft quit failed for {target}",
        }

    return {
        "status": "failed",
        "task_id": task_id,
        "action": action,
        "instance": instance,
        "error": f"unsupported action: {action}",
    }
