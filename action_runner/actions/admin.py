from __future__ import annotations

import json
from typing import Any

from ..admin_audit import analyze_admin_audit_text, extract_log_path_from_prefixed_output
from ..tools import ssh_run
from .types import ActionResult

DEFAULT_ADMIN_AUDIT_HOST = "admin"
DEFAULT_ADMIN_AUDIT_COMMAND = "sudo /usr/local/bin/mac_audit.sh"
DEFAULT_ADMIN_AUDIT_TIMEOUT_SECONDS = 120
DEFAULT_VERIFY_TIMEOUT_SECONDS = 30
DEFAULT_VERIFY_MAX_AGE_SECONDS = 1800
DEFAULT_ANALYZE_TIMEOUT_SECONDS = 30
DEFAULT_ANALYZE_LOG_DIR = "/var/log/mac-audit"
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


def _require_host(payload: dict[str, Any]) -> str | ActionResult:
    host = str(payload.get("host", DEFAULT_ADMIN_AUDIT_HOST)).strip()
    if host:
        return host
    return ActionResult(
        status="failed",
        exit_code=1,
        stdout="",
        stderr="",
        error="payload.host is required",
    )


def _require_positive_int(payload: dict[str, Any], key: str, default: int) -> int | ActionResult:
    raw_value = payload.get(key, default)
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        return ActionResult(
            status="failed",
            exit_code=1,
            stdout="",
            stderr="",
            error=f"invalid {key}: {raw_value!r}",
        )

    if value <= 0:
        return ActionResult(
            status="failed",
            exit_code=1,
            stdout="",
            stderr="",
            error=f"{key} must be > 0",
        )
    return value


def run_admin_host_audit(payload: dict[str, Any]) -> ActionResult:
    host = _require_host(payload)
    if isinstance(host, ActionResult):
        return host

    timeout_seconds = _require_positive_int(payload, "timeout_seconds", DEFAULT_ADMIN_AUDIT_TIMEOUT_SECONDS)
    if isinstance(timeout_seconds, ActionResult):
        return timeout_seconds

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
    host = _require_host(payload)
    if isinstance(host, ActionResult):
        return host

    timeout_seconds = _require_positive_int(payload, "timeout_seconds", DEFAULT_VERIFY_TIMEOUT_SECONDS)
    if isinstance(timeout_seconds, ActionResult):
        return timeout_seconds

    max_age_seconds = _require_positive_int(payload, "max_age_seconds", DEFAULT_VERIFY_MAX_AGE_SECONDS)
    if isinstance(max_age_seconds, ActionResult):
        return max_age_seconds

    log_dir = str(payload.get("log_dir", DEFAULT_ANALYZE_LOG_DIR)).strip()
    if not log_dir:
        return ActionResult(
            status="failed",
            exit_code=1,
            stdout="",
            stderr="",
            error="payload.log_dir is required",
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


def analyze_admin_host_audit(payload: dict[str, Any]) -> ActionResult:
    host = _require_host(payload)
    if isinstance(host, ActionResult):
        return host

    timeout_seconds = _require_positive_int(payload, "timeout_seconds", DEFAULT_ANALYZE_TIMEOUT_SECONDS)
    if isinstance(timeout_seconds, ActionResult):
        return timeout_seconds

    log_dir = str(payload.get("log_dir", DEFAULT_ANALYZE_LOG_DIR)).strip()
    if not log_dir:
        return ActionResult(
            status="failed",
            exit_code=1,
            stdout="",
            stderr="",
            error="payload.log_dir is required",
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
        'echo "LOG_PATH:$latest"; '
        'echo "__AUDIT_BODY_BEGIN__"; '
        'cat "$latest"'
    )

    raw_result = ssh_run(
        host=host,
        command=command,
        timeout_seconds=timeout_seconds,
    )

    if raw_result.status != "success":
        return ActionResult(
            status="failed",
            exit_code=raw_result.exit_code,
            stdout=f"host={host} audit_analyze=failed",
            stderr=_tail_lines(raw_result.stderr, limit=20),
            error=raw_result.error or "failed to fetch audit log",
        )

    log_path, audit_text = extract_log_path_from_prefixed_output(raw_result.stdout)
    if not audit_text:
        return ActionResult(
            status="failed",
            exit_code=1,
            stdout=f"host={host} audit_analyze=failed",
            stderr="",
            error="audit log is empty or audit body marker is missing",
        )

    analysis = analyze_admin_audit_text(audit_text, log_path=log_path)

    result_payload = {
        "analysis_level": analysis.overall,
        "analysis_findings_count": len(analysis.findings),
        "analysis_summary": "; ".join(f"{f.severity}:{f.message}" for f in analysis.findings),
        "analysis_log_path": analysis.log_path or "",
    }

    summary = (
        f"{analysis.render_summary(host=host)}\n"
        f"RESULT_JSON:{json.dumps(result_payload, ensure_ascii=False, sort_keys=True)}"
    )

    return ActionResult(
        status="success",
        exit_code=analysis.exit_code,
        stdout=summary,
        stderr="",
        error=None,
    )
