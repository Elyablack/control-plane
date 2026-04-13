from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..config import OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_OPS_BRIEF_MODEL
from .types import ActionResult

DEFAULT_MODEL = OPENAI_OPS_BRIEF_MODEL
DEFAULT_BRIEF_DIR = "/srv/control-plane/state/reviews/briefs"


@dataclass(frozen=True, slots=True)
class OpsBriefPaths:
    json_path: str
    markdown_path: str


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _utc_text(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")


def _safe_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2)


def _brief_schema() -> dict[str, Any]:
    return {
        "name": "ops_incident_brief",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "brief_status": {
                    "type": "string",
                    "enum": ["stable", "watch", "risky"],
                },
                "executive_summary": {"type": "string"},
                "top_risks": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "recommended_actions": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "operator_note": {"type": "string"},
            },
            "required": [
                "brief_status",
                "executive_summary",
                "top_risks",
                "recommended_actions",
                "operator_note",
            ],
        },
    }


def _extract_output_text(response_json: dict[str, Any]) -> str:
    output_text = response_json.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

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


def _call_openai_ops_brief(brief_input: dict[str, Any], *, model: str) -> dict[str, Any]:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not set")

    schema = _brief_schema()

    developer_prompt = (
        "You are a concise operations assistant for a small self-hosted control-plane. "
        "You receive one structured audit/analyzer result and must produce a short, practical incident brief. "
        "Do not overreact. Distinguish real risk from mild noise. "
        "Do not suggest broad rewrites. Prefer bounded operator-friendly next steps."
    )

    user_prompt = (
        "Create a short operational brief for this analyzer result.\n"
        "Environment: small self-hosted control-plane.\n"
        "Input JSON:\n"
        f"{_json_text(brief_input)}"
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
        with urllib.request.urlopen(req, timeout=60) as resp:
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
        raise RuntimeError(f"OpenAI returned non-JSON brief: {output_text}") from exc

    if not isinstance(parsed, dict):
        raise RuntimeError("OpenAI returned brief JSON that is not an object")

    return parsed


def _render_markdown(brief_input: dict[str, Any], brief: dict[str, Any], *, generated_at_utc: str) -> str:
    lines: list[str] = [
        "# Ops incident brief",
        "",
        f"- Generated at: {generated_at_utc}",
        f"- Source: {brief_input.get('source', '')}",
        f"- Analysis level: {brief_input.get('analysis_level', '')}",
        f"- Findings count: {brief_input.get('analysis_findings_count', 0)}",
        f"- Log path: {brief_input.get('analysis_log_path', '')}",
        f"- Brief status: {brief.get('brief_status', '')}",
        "",
        "## Analyzer summary",
        "",
        brief_input.get("analysis_summary", ""),
        "",
        "## Executive summary",
        "",
        brief.get("executive_summary", ""),
        "",
        "## Top risks",
        "",
    ]

    for item in brief.get("top_risks", []):
        lines.append(f"- {item}")

    lines.extend(["", "## Recommended actions", ""])
    for item in brief.get("recommended_actions", []):
        lines.append(f"- {item}")

    lines.extend(["", "## Operator note", "", brief.get("operator_note", ""), ""])

    facts = brief_input.get("facts", {})
    if isinstance(facts, dict) and facts:
        lines.extend(["## Facts", ""])
        for key in sorted(facts):
            lines.append(f"- {key}: {facts[key]}")
        lines.append("")

    context = brief_input.get("context", {})
    if isinstance(context, dict) and context:
        lines.extend(["## Context", ""])
        for key in sorted(context):
            lines.append(f"- {key}: {context[key]}")
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def _write_brief_files(
    *,
    brief_dir: str,
    source: str,
    now: datetime,
    brief_input: dict[str, Any],
    brief: dict[str, Any],
) -> OpsBriefPaths:
    stamp = now.astimezone(UTC).strftime("%Y-%m-%d_%H-%M-%S")
    safe_source = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in source).strip("_") or "unknown"

    target_dir = Path(brief_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    json_path = target_dir / f"brief-{safe_source}-{stamp}.json"
    markdown_path = target_dir / f"brief-{safe_source}-{stamp}.md"

    latest_json_link = target_dir / f"brief-{safe_source}-latest.json"
    latest_md_link = target_dir / f"brief-{safe_source}-latest.md"

    payload = {
        "generated_at_utc": _utc_text(now),
        "input": brief_input,
        "brief": brief,
    }

    json_path.write_text(_json_text(payload) + "\n", encoding="utf-8")
    markdown_path.write_text(
        _render_markdown(brief_input, brief, generated_at_utc=_utc_text(now)),
        encoding="utf-8",
    )

    for link_path, real_path in (
        (latest_json_link, json_path),
        (latest_md_link, markdown_path),
    ):
        if link_path.exists() or link_path.is_symlink():
            link_path.unlink()
        link_path.symlink_to(real_path.name)

    return OpsBriefPaths(json_path=str(json_path), markdown_path=str(markdown_path))


def generate_ai_ops_brief(payload: dict[str, Any]) -> ActionResult:
    source = _safe_str(payload.get("source"), "unknown")
    analysis_level = _safe_str(payload.get("analysis_level")).lower()
    analysis_summary = _safe_str(payload.get("analysis_summary"))
    analysis_findings_count = _safe_int(payload.get("analysis_findings_count"), 0)
    analysis_log_path = _safe_str(payload.get("analysis_log_path"))
    facts = _safe_dict(payload.get("facts"))
    context = _safe_dict(payload.get("context"))
    brief_dir = _safe_str(payload.get("brief_dir"), DEFAULT_BRIEF_DIR)
    model = _safe_str(payload.get("model"), DEFAULT_MODEL)

    if analysis_level not in {"warning", "critical"}:
        return ActionResult(
            status="skipped",
            exit_code=0,
            stdout=(
                f"ops_brief=skipped source={source} analysis_level={analysis_level or 'unknown'} "
                "reason=analysis_level_not_actionable"
            ),
            stderr="",
            error=None,
        )

    if not analysis_summary:
        return ActionResult(
            status="failed",
            exit_code=1,
            stdout="",
            stderr="",
            error="analysis_summary is required",
        )

    brief_input = {
        "source": source,
        "analysis_level": analysis_level,
        "analysis_summary": analysis_summary,
        "analysis_findings_count": analysis_findings_count,
        "analysis_log_path": analysis_log_path,
        "facts": facts,
        "context": context,
    }

    now = _utc_now()

    try:
        brief = _call_openai_ops_brief(brief_input, model=model)
        paths = _write_brief_files(
            brief_dir=brief_dir,
            source=source,
            now=now,
            brief_input=brief_input,
            brief=brief,
        )
    except Exception as exc:
        return ActionResult(
            status="failed",
            exit_code=1,
            stdout="",
            stderr="",
            error=str(exc),
        )

    result_payload = {
        "source": source,
        "brief_status": _safe_str(brief.get("brief_status")),
        "executive_summary": _safe_str(brief.get("executive_summary")),
        "markdown_path": paths.markdown_path,
        "json_path": paths.json_path,
    }

    stdout = (
        f"ops_brief=ok source={source} analysis_level={analysis_level} "
        f"brief_status={result_payload['brief_status']} markdown_path={paths.markdown_path}\n"
        f"RESULT_JSON:{json.dumps(result_payload, ensure_ascii=False, sort_keys=True)}"
    )

    return ActionResult(
        status="success",
        exit_code=0,
        stdout=stdout,
        stderr="",
        error=None,
    )
