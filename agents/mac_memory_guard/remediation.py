from __future__ import annotations

import json
import subprocess
from typing import Any

from .logging_utils import log_error, log_info, log_warn

PROTECTED_APPS = {
    "ChatGPT",
    "Terminal",
    "iTerm",
}


def _normalize_app_name(name: str) -> str:
    return " ".join(str(name or "").strip().split())


def _list_running_apps_with_pid() -> list[dict[str, Any]]:
    script = r'''
    tell application "System Events"
        set app_info to {}
        repeat with p in (every application process whose background only is false)
            set end of app_info to ((name of p as text) & tab & (unix id of p as text))
        end repeat
    end tell

    set {oldTID, AppleScript's text item delimiters} to {AppleScript's text item delimiters, linefeed}
    set output_text to app_info as text
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
            log_info("running_apps_empty")
            return []

        apps: list[dict[str, Any]] = []
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue

            parts = line.split("\t")
            if len(parts) != 2:
                continue

            name = _normalize_app_name(parts[0])
            try:
                pid = int(parts[1].strip())
            except ValueError:
                continue

            if not name or pid <= 0:
                continue

            apps.append({"name": name, "pid": pid})

        log_info("running_apps_loaded", count=len(apps))
        return apps

    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.strip() if exc.stderr else ""
        stdout = exc.stdout.strip() if exc.stdout else ""
        log_error("running_apps_failed", stdout=stdout, stderr=stderr)
        return []


def _rss_kb_for_pid(pid: int) -> int | None:
    try:
        result = subprocess.run(
            ["ps", "-o", "rss=", "-p", str(pid)],
            capture_output=True,
            text=True,
            check=True,
        )
        raw = result.stdout.strip()
        if not raw:
            return None
        return int(raw)
    except Exception:
        return None


def _select_highest_rss_candidate() -> dict[str, Any] | None:
    running = _list_running_apps_with_pid()
    if not running:
        log_info("candidate_selection_skipped", reason="no running apps visible")
        return None

    candidates: list[dict[str, Any]] = []

    for app in running:
        name = _normalize_app_name(app["name"])
        pid = int(app["pid"])

        if name in PROTECTED_APPS:
            continue

        rss_kb = _rss_kb_for_pid(pid)
        if rss_kb is None:
            continue

        candidates.append(
            {
                "name": name,
                "pid": pid,
                "rss_kb": rss_kb,
                "rss_mb": round(rss_kb / 1024.0, 1),
            }
        )

    if not candidates:
        log_info(
            "candidate_selection_skipped",
            reason="no eligible running app found after protection filter",
        )
        return None

    candidates.sort(key=lambda item: (item["rss_kb"], item["name"]), reverse=True)
    selected = candidates[0]

    log_info(
        "candidate_selected",
        target=selected["name"],
        pid=selected["pid"],
        rss_kb=selected["rss_kb"],
        rss_mb=selected["rss_mb"],
    )
    return selected


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
        log_error("remediation_invalid_payload", task_id=task_id, error=str(exc))
        return {
            "status": "failed",
            "task_id": task_id,
            "error": f"invalid task payload: {exc}",
        }

    action = str(payload.get("action", "")).strip()
    instance = str(payload.get("instance", "")).strip()

    log_info(
        "remediation_start",
        task_id=task_id,
        action=action,
        instance=instance,
    )

    if action == "soft_quit_allowlisted_candidate":
        candidate = _select_highest_rss_candidate()
        if candidate is None:
            log_info(
                "remediation_skipped",
                task_id=task_id,
                action=action,
                instance=instance,
                reason="no eligible running app found after protection filter",
            )
            return {
                "status": "skipped",
                "task_id": task_id,
                "action": action,
                "instance": instance,
                "reason": "no eligible running app found after protection filter",
            }

        target = candidate["name"]
        ok, stdout, stderr = _soft_quit(target)
        if ok:
            log_info(
                "remediation_success",
                task_id=task_id,
                action=action,
                target=target,
                pid=candidate["pid"],
                rss_kb=candidate["rss_kb"],
                rss_mb=candidate["rss_mb"],
                instance=instance,
            )
            return {
                "status": "success",
                "task_id": task_id,
                "action": action,
                "target": target,
                "pid": candidate["pid"],
                "rss_kb": candidate["rss_kb"],
                "rss_mb": candidate["rss_mb"],
                "instance": instance,
            }

        log_error(
            "remediation_failed",
            task_id=task_id,
            action=action,
            target=target,
            pid=candidate["pid"],
            rss_kb=candidate["rss_kb"],
            rss_mb=candidate["rss_mb"],
            instance=instance,
            stdout=stdout,
            stderr=stderr,
        )
        return {
            "status": "failed",
            "task_id": task_id,
            "action": action,
            "target": target,
            "pid": candidate["pid"],
            "rss_kb": candidate["rss_kb"],
            "rss_mb": candidate["rss_mb"],
            "instance": instance,
            "stdout": stdout,
            "stderr": stderr,
            "error": f"soft quit failed for {target}",
        }

    if action == "soft_quit":
        target = _normalize_app_name(str(payload.get("target", "")).strip())

        if not target:
            log_error(
                "remediation_failed",
                task_id=task_id,
                action=action,
                instance=instance,
                error="missing target",
            )
            return {
                "status": "failed",
                "task_id": task_id,
                "action": action,
                "instance": instance,
                "error": "missing target",
            }

        if target in PROTECTED_APPS:
            log_warn(
                "remediation_skipped",
                task_id=task_id,
                action=action,
                target=target,
                instance=instance,
                reason=f"target is protected: {target}",
            )
            return {
                "status": "skipped",
                "task_id": task_id,
                "action": action,
                "target": target,
                "instance": instance,
                "reason": f"target is protected: {target}",
            }

        ok, stdout, stderr = _soft_quit(target)
        if ok:
            log_info(
                "remediation_success",
                task_id=task_id,
                action=action,
                target=target,
                instance=instance,
            )
            return {
                "status": "success",
                "task_id": task_id,
                "action": action,
                "target": target,
                "instance": instance,
            }

        log_error(
            "remediation_failed",
            task_id=task_id,
            action=action,
            target=target,
            instance=instance,
            stdout=stdout,
            stderr=stderr,
        )
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

    log_error(
        "remediation_failed",
        task_id=task_id,
        action=action,
        instance=instance,
        error=f"unsupported action: {action}",
    )
    return {
        "status": "failed",
        "task_id": task_id,
        "action": action,
        "instance": instance,
        "error": f"unsupported action: {action}",
    }
