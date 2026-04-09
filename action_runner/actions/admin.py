from __future__ import annotations

from typing import Any

from ..tools import ssh_run
from .types import ActionResult

DEFAULT_ADMIN_AUDIT_HOST = "admin"
DEFAULT_ADMIN_AUDIT_COMMAND = "sudo /usr/local/bin/mac_audit.sh"
DEFAULT_ADMIN_AUDIT_TIMEOUT_SECONDS = 120
DEFAULT_VERIFY_TIMEOUT_SECONDS = 30
DEFAULT_VERIFY_MAX_AGE_SECONDS = 1800
MAX_STDOUT_TAIL_LINES = 20
SAVED_PREFIX = "Saved: "


def _tail_lines(text: str, limit: int = MAX_STDOUT_TAIL_LINES) -> str:
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return ""
    return "\n".join(lines[-limit:])


def _extract_saved_log_path(stdout: str) -> str | None:
    for line in reversed(stdout.splitlines()):
        stripped = line.strip()
        if stripped.startswith(SAVED_PREFIX):
            path = stripped.removeprefix(SAVED_PREFIX).strip()
            return path or None
    return None


def run_admin_host_audit(payload: dict[str, Any]) -> ActionResult:
    raw_host = payload.get("host", DEFAULT_ADMIN_AUDIT_HOST)
    raw_timeout = payload.get("timeout_seconds", DEFAULT_ADMIN_AUDIT_TIMEOUT_SECONDS)

    host = str(raw_host).strip()
    if not host:
        return ActionResult(
            status="failed",
            exit_code=1,
            stdout="",
            stderr="",
            error="payload.host is required",
        )

    try:
        timeout_seconds = int(raw_timeout)
    except (TypeError, ValueError):
        return ActionResult(
            status="failed",
            exit_code=1,
            stdout="",
            stderr="",
            error=f"invalid timeout_seconds: {raw_timeout!r}",
        )

    if timeout_seconds <= 0:
        return ActionResult(
            status="failed",
            exit_code=1,
            stdout="",
            stderr="",
            error="timeout_seconds must be > 0",
        )

    raw_result = ssh_run(
        host=host,
        command=DEFAULT_ADMIN_AUDIT_COMMAND,
        timeout_seconds=timeout_seconds,
    )

    log_path = _extract_saved_log_path(raw_result.stdout)
    stdout_tail = _tail_lines(raw_result.stdout)

    if raw_result.status == "success":
        summary_parts = [
            f"host={host}",
            "audit=completed",
        ]
        if log_path:
            summary_parts.append(f"log_path={log_path}")

        return ActionResult(
            status="success",
            exit_code=raw_result.exit_code,
            stdout=" ".join(summary_parts),
            stderr="",
            error=None,
        )

    failure_parts = [
        f"host={host}",
        "audit=failed",
    ]
    if log_path:
        failure_parts.append(f"log_path={log_path}")

    failure_summary = " ".join(failure_parts)
    if stdout_tail:
        failure_summary = f"{failure_summary}\n\nstdout_tail:\n{stdout_tail}"

    return ActionResult(
        status="failed",
        exit_code=raw_result.exit_code,
        stdout=failure_summary,
        stderr=_tail_lines(raw_result.stderr, limit=20),
        error=raw_result.error,
    )


def verify_admin_host_audit(payload: dict[str, Any]) -> ActionResult:
    raw_host = payload.get("host", DEFAULT_ADMIN_AUDIT_HOST)
    raw_timeout = payload.get("timeout_seconds", DEFAULT_VERIFY_TIMEOUT_SECONDS)
    raw_max_age = payload.get("max_age_seconds", DEFAULT_VERIFY_MAX_AGE_SECONDS)
    raw_log_dir = payload.get("log_dir", "/var/log/mac-audit")

    host = str(raw_host).strip()
    log_dir = str(raw_log_dir).strip()

    if not host:
        return ActionResult(
            status="failed",
            exit_code=1,
            stdout="",
            stderr="",
            error="payload.host is required",
        )

    if not log_dir:
        return ActionResult(
            status="failed",
            exit_code=1,
            stdout="",
            stderr="",
            error="payload.log_dir is required",
        )

    try:
        timeout_seconds = int(raw_timeout)
        max_age_seconds = int(raw_max_age)
    except (TypeError, ValueError):
        return ActionResult(
            status="failed",
            exit_code=1,
            stdout="",
            stderr="",
            error=f"invalid timeout or max_age: timeout={raw_timeout!r} max_age={raw_max_age!r}",
        )

    if timeout_seconds <= 0:
        return ActionResult(
            status="failed",
            exit_code=1,
            stdout="",
            stderr="",
            error="timeout_seconds must be > 0",
        )

    if max_age_seconds <= 0:
        return ActionResult(
            status="failed",
            exit_code=1,
            stdout="",
            stderr="",
            error="max_age_seconds must be > 0",
        )

    command = (
        "set -euo pipefail; "
        f'latest="$(ls -1t {log_dir}/audit_*.log 2>/dev/null | head -n1)"; '
        'if [ -z "${latest:-}" ]; then '
        '  echo "NO_LOG"; '
        "  exit 12; "
        "fi; "
        'if [ ! -s "$latest" ]; then '
        '  echo "EMPTY_LOG|$latest"; '
        "  exit 13; "
        "fi; "
        'mtime="$(stat -c %Y "$latest")"; '
        'now="$(date +%s)"; '
        'age="$((now - mtime))"; '
        'echo "OK|$latest|$mtime|$age"'
    )

    raw_result = ssh_run(
        host=host,
        command=command,
        timeout_seconds=timeout_seconds,
    )

    line = raw_result.stdout.strip()

    if raw_result.status != "success":
        return ActionResult(
            status="failed",
            exit_code=raw_result.exit_code,
            stdout=f"host={host} audit_verify=failed",
            stderr=_tail_lines(raw_result.stderr, limit=20),
            error=raw_result.error or f"verify command failed: {line}",
        )

    if not line.startswith("OK|"):
        return ActionResult(
            status="failed",
            exit_code=1,
            stdout=f"host={host} audit_verify=failed",
            stderr="",
            error=f"unexpected verify output: {line or 'empty output'}",
        )

    parts = line.split("|", 3)
    if len(parts) != 4:
        return ActionResult(
            status="failed",
            exit_code=1,
            stdout=f"host={host} audit_verify=failed",
            stderr="",
            error=f"invalid verify output format: {line}",
        )

    _, latest_log, mtime_unix, age_s = parts

    try:
        age_seconds = int(age_s)
    except ValueError:
        return ActionResult(
            status="failed",
            exit_code=1,
            stdout=f"host={host} audit_verify=failed",
            stderr="",
            error=f"invalid audit log age: {age_s!r}",
        )

    if age_seconds > max_age_seconds:
        return ActionResult(
            status="failed",
            exit_code=14,
            stdout=(
                f"host={host} audit_verify=failed "
                f"log_path={latest_log} log_age_s={age_seconds} "
                f"max_age_s={max_age_seconds}"
            ),
            stderr="",
            error="latest audit log is too old",
        )

    return ActionResult(
        status="success",
        exit_code=0,
        stdout=(
            f"host={host} audit_verify=ok "
            f"log_path={latest_log} "
            f"log_mtime_unix={mtime_unix} "
            f"log_age_s={age_seconds}"
        ),
        stderr="",
        error=None,
    )
