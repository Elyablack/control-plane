from __future__ import annotations

import json
import re
import sqlite3
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from ..config import OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_WEEKLY_REVIEW_MODEL
from .types import ActionResult

DEFAULT_DB_PATH = "/srv/control-plane/state/action_runner.db"
DEFAULT_REVIEW_DIR = "/srv/control-plane/state/reviews"
DEFAULT_MODEL = OPENAI_WEEKLY_REVIEW_MODEL
DEFAULT_DAYS = 7
DEFAULT_RETENTION_COUNT = 10

EXCLUDED_ALERTNAMES = {
    "AdminHostAuditWeekly",
    "HostRebootDetected",
}
EXCLUDED_ALERT_PREFIXES = (
    "Demo",
)
EXCLUDED_SEVERITIES = {
    "ok",
}
EXCLUDED_FAILURE_ACTIONS = {
    "generate_weekly_ops_review",
    "notify_email",
}
INCLUDED_OPERATIONAL_ACTIONS = {
    "run_backup",
    "verify_backup",
    "run_admin_host_audit",
    "verify_admin_host_audit",
    "analyze_admin_host_audit",
    "notify_tg",
    "enqueue_mac_action",
}
LEGACY_AUDIT_SUMMARY_PATTERNS = (
    "infra-backups path missing",
    "infra-backups tar/sha256 counts do not match",
    "backup path missing",
    "backup path not writable",
    "backup configs age",
)


@dataclass(frozen=True, slots=True)
class WeeklyReviewPaths:
    json_path: str
    markdown_path: str


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _utc_text(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")


def _safe_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed


def _query_rows(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
    cur = conn.execute(sql, params)
    return list(cur.fetchall())


def _query_value(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...] = (), *, default: Any = None) -> Any:
    cur = conn.execute(sql, params)
    row = cur.fetchone()
    if row is None:
        return default
    if isinstance(row, sqlite3.Row):
        values = tuple(row)
        return values[0] if values else default
    return row[0] if row else default


def _extract_result_json(stdout: str) -> dict[str, Any] | None:
    if not stdout:
        return None

    match = re.search(r"RESULT_JSON:(\{.*\})", stdout, flags=re.DOTALL)
    if not match:
        return None

    try:
        parsed = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None

    return parsed if isinstance(parsed, dict) else None


def _is_excluded_alert(alertname: str, severity: str) -> bool:
    if not alertname:
        return True

    if severity in EXCLUDED_SEVERITIES:
        return True

    if alertname in EXCLUDED_ALERTNAMES:
        return True

    return any(alertname.startswith(prefix) for prefix in EXCLUDED_ALERT_PREFIXES)


def _is_operational_failure_action(action: str) -> bool:
    if not action:
        return False
    if action in EXCLUDED_FAILURE_ACTIONS:
        return False
    return action in INCLUDED_OPERATIONAL_ACTIONS


def _split_findings(summary: str) -> list[str]:
    text = (summary or "").strip()
    if not text:
        return []
    return [part.strip() for part in text.split(";") if part.strip()]


def _is_legacy_audit_finding(finding: str) -> bool:
    lowered = finding.lower()
    return any(pattern in lowered for pattern in LEGACY_AUDIT_SUMMARY_PATTERNS)


def _clean_audit_summary(summary: str) -> str:
    cleaned = [finding for finding in _split_findings(summary) if not _is_legacy_audit_finding(finding)]
    return "; ".join(cleaned)


def _is_meaningful_audit_review(status: str, cleaned_summary: str, findings_count: int) -> bool:
    if status == "failed":
        return True
    if cleaned_summary:
        return True
    if findings_count > 0 and cleaned_summary:
        return True
    return False


def _prune_old_reviews(review_dir: str, *, retention_count: int) -> None:
    keep = max(retention_count, 1)
    target_dir = Path(review_dir)

    for suffix in ("json", "md"):
        review_files = sorted(
            target_dir.glob(f"weekly-*.{suffix}"),
            key=lambda path: path.name,
            reverse=True,
        )
        for old_path in review_files[keep:]:
            if old_path.name in {f"weekly-latest.{suffix}"}:
                continue
            old_path.unlink(missing_ok=True)


def _build_weekly_summary(*, db_path: str, since_utc: str, until_utc: str) -> dict[str, Any]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        decisions_total = _query_value(
            conn,
            "select count(*) from decisions where created_at >= ? and created_at <= ?",
            (since_utc, until_utc),
            default=0,
        )

        tasks_total = _query_value(
            conn,
            "select count(*) from tasks where created_at >= ? and created_at <= ?",
            (since_utc, until_utc),
            default=0,
        )

        runs_total = _query_value(
            conn,
            "select count(*) from runs where started_at >= ? and started_at <= ?",
            (since_utc, until_utc),
            default=0,
        )

        decisions_by_type_rows = _query_rows(
            conn,
            """
            select decision, count(*) as count
            from decisions
            where created_at >= ? and created_at <= ?
            group by decision
            order by count desc, decision asc
            """,
            (since_utc, until_utc),
        )
        decisions_by_type = {row["decision"]: row["count"] for row in decisions_by_type_rows}

        top_alert_rows = _query_rows(
            conn,
            """
            select alertname, severity, count(*) as count
            from decisions
            where created_at >= ? and created_at <= ?
            group by alertname, severity
            order by count desc, alertname asc
            """,
            (since_utc, until_utc),
        )
        top_alerts = [
            {
                "alertname": row["alertname"],
                "severity": row["severity"],
                "count": row["count"],
            }
            for row in top_alert_rows
            if not _is_excluded_alert(str(row["alertname"] or ""), str(row["severity"] or ""))
        ][:10]

        task_status_rows = _query_rows(
            conn,
            """
            select task_type, status, count(*) as count
            from tasks
            where created_at >= ? and created_at <= ?
            group by task_type, status
            order by task_type asc, count desc
            """,
            (since_utc, until_utc),
        )
        task_status_counts = [
            {
                "task_type": row["task_type"],
                "status": row["status"],
                "count": row["count"],
            }
            for row in task_status_rows
            if row["status"] not in {"running"}
        ]

        run_status_rows = _query_rows(
            conn,
            """
            select action, status, count(*) as count
            from runs
            where started_at >= ? and started_at <= ?
            group by action, status
            order by action asc, count desc
            """,
            (since_utc, until_utc),
        )
        run_status_counts = [
            {
                "action": row["action"],
                "status": row["status"],
                "count": row["count"],
            }
            for row in run_status_rows
            if row["status"] not in {"running", "skipped"}
            and str(row["action"] or "") not in EXCLUDED_FAILURE_ACTIONS
        ]

        backup_rows = _query_rows(
            conn,
            """
            select id, action, status, started_at, finished_at, exit_code, error
            from runs
            where action in ('run_backup', 'verify_backup')
              and started_at >= ? and started_at <= ?
              and status not in ('running', 'skipped')
            order by started_at desc
            limit 50
            """,
            (since_utc, until_utc),
        )
        backup_runs = [
            {
                "id": row["id"],
                "action": row["action"],
                "status": row["status"],
                "started_at": row["started_at"],
                "finished_at": row["finished_at"],
                "exit_code": row["exit_code"],
                "error": row["error"] or "",
            }
            for row in backup_rows
        ]

        audit_rows = _query_rows(
            conn,
            """
            select id, status, started_at, finished_at, exit_code, stdout, error
            from runs
            where action = 'analyze_admin_host_audit'
              and started_at >= ? and started_at <= ?
              and status != 'running'
            order by started_at desc
            limit 30
            """,
            (since_utc, until_utc),
        )
        audit_reviews: list[dict[str, Any]] = []
        for row in audit_rows:
            result_json = _extract_result_json(row["stdout"] or "")
            raw_summary = (result_json or {}).get("analysis_summary", "")
            cleaned_summary = _clean_audit_summary(raw_summary)
            findings_count = len(_split_findings(cleaned_summary))

            if not _is_meaningful_audit_review(str(row["status"] or ""), cleaned_summary, findings_count):
                continue

            audit_reviews.append(
                {
                    "id": row["id"],
                    "status": row["status"],
                    "started_at": row["started_at"],
                    "finished_at": row["finished_at"],
                    "exit_code": row["exit_code"],
                    "error": row["error"] or "",
                    "analysis_level": (result_json or {}).get("analysis_level", ""),
                    "analysis_findings_count": findings_count,
                    "analysis_summary": cleaned_summary,
                    "analysis_log_path": (result_json or {}).get("analysis_log_path", ""),
                }
            )

        mac_alert_rows = _query_rows(
            conn,
            """
            select id, alertname, severity, summary, decision, reason, created_at
            from decisions
            where alertname = 'MacMemoryPressure'
              and created_at >= ? and created_at <= ?
            order by created_at desc
            limit 80
            """,
            (since_utc, until_utc),
        )
        mac_alerts = [
            {
                "id": row["id"],
                "severity": row["severity"],
                "summary": row["summary"],
                "decision": row["decision"],
                "reason": row["reason"],
                "created_at": row["created_at"],
            }
            for row in mac_alert_rows
            if str(row["severity"] or "") not in EXCLUDED_SEVERITIES
            and "synthetic" not in str(row["summary"] or "").lower()
        ]

        mac_action_rows = _query_rows(
            conn,
            """
            select id, task_type, status, payload, result_json, created_at, finished_at, error
            from tasks
            where task_type = 'mac_action'
              and created_at >= ? and created_at <= ?
              and status != 'running'
            order by created_at desc
            limit 50
            """,
            (since_utc, until_utc),
        )
        mac_actions = []
        for row in mac_action_rows:
            result_json: dict[str, Any] = {}
            try:
                parsed = json.loads(row["result_json"]) if row["result_json"] else {}
                if isinstance(parsed, dict):
                    result_json = parsed
            except json.JSONDecodeError:
                result_json = {}

            mac_actions.append(
                {
                    "id": row["id"],
                    "status": row["status"],
                    "created_at": row["created_at"],
                    "finished_at": row["finished_at"],
                    "error": row["error"] or "",
                    "action": result_json.get("action", ""),
                    "target": result_json.get("target", ""),
                    "result_status": result_json.get("status", ""),
                    "rss_mb": result_json.get("rss_mb"),
                }
            )

        latest_failure_rows = _query_rows(
            conn,
            """
            select id, action, status, started_at, finished_at, exit_code, error
            from runs
            where started_at >= ? and started_at <= ?
              and status = 'failed'
            order by started_at desc
            limit 50
            """,
            (since_utc, until_utc),
        )
        latest_failures = [
            {
                "id": row["id"],
                "action": row["action"],
                "status": row["status"],
                "started_at": row["started_at"],
                "finished_at": row["finished_at"],
                "exit_code": row["exit_code"],
                "error": row["error"] or "",
            }
            for row in latest_failure_rows
            if _is_operational_failure_action(str(row["action"] or ""))
        ][:15]

        summary = {
            "window": {
                "since_utc": since_utc,
                "until_utc": until_utc,
            },
            "totals": {
                "decisions": decisions_total,
                "tasks": tasks_total,
                "runs": runs_total,
            },
            "decisions_by_type": decisions_by_type,
            "top_alerts": top_alerts,
            "task_status_counts": task_status_counts,
            "run_status_counts": run_status_counts,
            "backup_runs": backup_runs,
            "admin_audit_reviews": audit_reviews,
            "mac_memory_alerts": mac_alerts,
            "mac_remediation_tasks": mac_actions,
            "latest_failures": latest_failures,
        }
        return summary
    finally:
        conn.close()


def _weekly_review_schema() -> dict[str, Any]:
    return {
        "name": "weekly_ops_review",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "week_status": {
                    "type": "string",
                    "enum": ["quiet", "stable", "watch", "risky"],
                },
                "executive_summary": {
                    "type": "string",
                },
                "top_issues": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "title": {"type": "string"},
                            "severity": {"type": "string"},
                            "evidence": {"type": "string"},
                        },
                        "required": ["title", "severity", "evidence"],
                    },
                },
                "recurring_patterns": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "noise_or_expected": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "recommended_actions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "priority": {"type": "string"},
                            "action": {"type": "string"},
                            "why": {"type": "string"},
                        },
                        "required": ["priority", "action", "why"],
                    },
                },
            },
            "required": [
                "week_status",
                "executive_summary",
                "top_issues",
                "recurring_patterns",
                "noise_or_expected",
                "recommended_actions",
            ],
        },
    }


def _extract_output_text(response_json: dict[str, Any]) -> str:
    if isinstance(response_json.get("output_text"), str) and response_json["output_text"].strip():
        return response_json["output_text"].strip()

    output = response_json.get("output", [])
    if not isinstance(output, list):
        return ""

    chunks: list[str] = []
    for item in output:
        if not isinstance(item, dict):
            continue
        content = item.get("content", [])
        if not isinstance(content, list):
            continue
        for part in content:
            if not isinstance(part, dict):
                continue
            text = part.get("text")
            if isinstance(text, str) and text.strip():
                chunks.append(text.strip())

    return "\n".join(chunks).strip()


def _call_openai_weekly_review(summary: dict[str, Any], *, model: str) -> dict[str, Any]:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not set")

    schema = _weekly_review_schema()

    developer_prompt = (
        "You are an operations reviewer for a small self-hosted control-plane. "
        "Analyze the weekly operational summary and produce a concise, practical review. "
        "Focus on recurring issues, real risk, and small high-value improvements. "
        "Do not suggest broad rewrites unless clearly justified. "
        "Legacy backup-path noise, test/demo alerts, self-review setup failures, and running/skipped runs "
        "have already been filtered from the input."
    )

    user_prompt = (
        "Review this 7-day operations summary.\n"
        "Environment: small single-VPS control-plane with bounded automation.\n"
        "Be conservative, practical, and avoid overengineering.\n\n"
        "Weekly summary JSON:\n"
        f"{json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2)}"
    )

    payload = {
        "model": model,
        "input": [
            {
                "role": "developer",
                "content": [{"type": "input_text", "text": developer_prompt}],
            },
            {
                "role": "user",
                "content": [{"type": "input_text", "text": user_prompt}],
            },
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": schema["name"],
                "strict": schema["strict"],
                "schema": schema["schema"],
            }
        },
    }

    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{OPENAI_BASE_URL}/responses",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json; charset=utf-8",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            response_json = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI HTTP error {exc.code}: {error_body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"OpenAI request failed: {exc}") from exc

    output_text = _extract_output_text(response_json)
    if not output_text:
        raise RuntimeError("OpenAI response did not contain output_text")

    try:
        parsed = json.loads(output_text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"OpenAI returned non-JSON review: {output_text}") from exc

    if not isinstance(parsed, dict):
        raise RuntimeError("OpenAI returned review JSON that is not an object")

    return parsed


def _render_markdown(summary: dict[str, Any], review: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Weekly ops review")
    lines.append("")
    lines.append(f"- Window start: {summary['window']['since_utc']}")
    lines.append(f"- Window end: {summary['window']['until_utc']}")
    lines.append(f"- Week status: {review.get('week_status', 'unknown')}")
    lines.append("")
    lines.append("## Executive summary")
    lines.append("")
    lines.append(review.get("executive_summary", ""))
    lines.append("")
    lines.append("## Top issues")
    lines.append("")

    for item in review.get("top_issues", []):
        lines.append(f"- **{item.get('title', '')}** [{item.get('severity', '')}]")
        lines.append(f"  - evidence: {item.get('evidence', '')}")

    lines.append("")
    lines.append("## Recurring patterns")
    lines.append("")
    for item in review.get("recurring_patterns", []):
        lines.append(f"- {item}")

    lines.append("")
    lines.append("## Noise or expected")
    lines.append("")
    for item in review.get("noise_or_expected", []):
        lines.append(f"- {item}")

    lines.append("")
    lines.append("## Recommended actions")
    lines.append("")
    for item in review.get("recommended_actions", []):
        lines.append(f"- **{item.get('priority', '')}**: {item.get('action', '')}")
        lines.append(f"  - why: {item.get('why', '')}")

    lines.append("")
    lines.append("## Raw counters")
    lines.append("")
    lines.append(f"- Decisions: {summary['totals']['decisions']}")
    lines.append(f"- Tasks: {summary['totals']['tasks']}")
    lines.append(f"- Runs: {summary['totals']['runs']}")

    return "\n".join(lines).strip() + "\n"


def _write_review_files(*, review_dir: str, now: datetime, summary: dict[str, Any], review: dict[str, Any]) -> WeeklyReviewPaths:
    stamp = now.astimezone(UTC).strftime("%Y-%m-%d_%H-%M-%S")
    target_dir = Path(review_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    json_path = target_dir / f"weekly-{stamp}.json"
    markdown_path = target_dir / f"weekly-{stamp}.md"

    latest_json_link = target_dir / "weekly-latest.json"
    latest_md_link = target_dir / "weekly-latest.md"

    json_payload = {
        "generated_at_utc": _utc_text(now),
        "summary": summary,
        "review": review,
    }

    json_path.write_text(json.dumps(json_payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(_render_markdown(summary, review), encoding="utf-8")

    for link_path, real_path in (
        (latest_json_link, json_path),
        (latest_md_link, markdown_path),
    ):
        if link_path.exists() or link_path.is_symlink():
            link_path.unlink()
        link_path.symlink_to(real_path.name)

    return WeeklyReviewPaths(json_path=str(json_path), markdown_path=str(markdown_path))


def generate_weekly_ops_review(payload: dict[str, Any]) -> ActionResult:
    days = _safe_int(payload.get("days"), DEFAULT_DAYS)
    if days <= 0:
        days = DEFAULT_DAYS

    retention_count = _safe_int(payload.get("retention_count"), DEFAULT_RETENTION_COUNT)
    if retention_count <= 0:
        retention_count = DEFAULT_RETENTION_COUNT

    db_path = str(payload.get("db_path", DEFAULT_DB_PATH)).strip() or DEFAULT_DB_PATH
    review_dir = str(payload.get("review_dir", DEFAULT_REVIEW_DIR)).strip() or DEFAULT_REVIEW_DIR
    model = str(payload.get("model", DEFAULT_MODEL)).strip() or DEFAULT_MODEL

    if not Path(db_path).exists():
        return ActionResult(
            status="failed",
            exit_code=1,
            stdout="",
            stderr="",
            error=f"database not found: {db_path}",
        )

    now = _utc_now()
    since = now - timedelta(days=days)
    since_utc = _utc_text(since)
    until_utc = _utc_text(now)

    try:
        summary = _build_weekly_summary(db_path=db_path, since_utc=since_utc, until_utc=until_utc)
        review = _call_openai_weekly_review(summary, model=model)
        paths = _write_review_files(
            review_dir=review_dir,
            now=now,
            summary=summary,
            review=review,
        )
        _prune_old_reviews(review_dir, retention_count=retention_count)
    except Exception as exc:
        return ActionResult(
            status="failed",
            exit_code=1,
            stdout="",
            stderr="",
            error=str(exc),
        )

    result_payload = {
        "markdown_path": paths.markdown_path,
    }

    stdout = (
        f"weekly_review=ok days={days} retention_count={retention_count} model={model} "
        f"markdown_path={paths.markdown_path}\n"
        f"RESULT_JSON:{json.dumps(result_payload, ensure_ascii=False, sort_keys=True)}"
    )

    return ActionResult(
        status="success",
        exit_code=0,
        stdout=stdout,
        stderr="",
        error=None,
    )
