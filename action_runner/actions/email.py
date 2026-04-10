from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ..config import (
    RESEND_API_KEY,
    RESEND_API_URL,
    RESEND_FROM,
    RESEND_TIMEOUT_SECONDS,
    RESEND_TO,
)
from .types import ActionResult


def _as_clean_str(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def notify_email(payload: dict[str, Any]) -> ActionResult:
    to_addr = _as_clean_str(payload.get("to") or RESEND_TO)
    subject = _as_clean_str(payload.get("subject"))
    body = _as_clean_str(payload.get("body"))
    from_addr = _as_clean_str(payload.get("from") or RESEND_FROM)

    if not RESEND_API_KEY:
        return ActionResult(
            status="failed",
            exit_code=1,
            stdout="",
            stderr="",
            error="RESEND_API_KEY is not configured",
        )

    if not from_addr:
        return ActionResult(
            status="failed",
            exit_code=1,
            stdout="",
            stderr="",
            error="email from address is required",
        )

    if not to_addr:
        return ActionResult(
            status="failed",
            exit_code=1,
            stdout="",
            stderr="",
            error="email recipient is required",
        )

    if not subject:
        return ActionResult(
            status="failed",
            exit_code=1,
            stdout="",
            stderr="",
            error="email subject is required",
        )

    if not body:
        return ActionResult(
            status="failed",
            exit_code=1,
            stdout="",
            stderr="",
            error="email body is required",
        )

    request_body = {
        "from": from_addr,
        "to": [to_addr],
        "subject": subject,
        "text": body,
    }

    raw_body = json.dumps(request_body).encode("utf-8")
    req = Request(
        RESEND_API_URL,
        data=raw_body,
        method="POST",
        headers={
            "Authorization": f"Bearer {RESEND_API_KEY}",
            "Content-Type": "application/json",
            "User-Agent": "control-plane/1.0",
        },
    )

    try:
        with urlopen(req, timeout=RESEND_TIMEOUT_SECONDS) as resp:
            response_text = resp.read().decode("utf-8", errors="replace")

        return ActionResult(
            status="success",
            exit_code=0,
            stdout=f"email_sent to={to_addr} subject={subject} response={response_text}",
            stderr="",
            error=None,
        )

    except HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")
        return ActionResult(
            status="failed",
            exit_code=exc.code,
            stdout="",
            stderr=body_text,
            error=f"resend api http error: {exc.code}",
        )
    except URLError as exc:
        return ActionResult(
            status="failed",
            exit_code=1,
            stdout="",
            stderr="",
            error=f"resend api network error: {exc.reason}",
        )
    except Exception as exc:
        return ActionResult(
            status="failed",
            exit_code=1,
            stdout="",
            stderr="",
            error=f"resend api unexpected error: {exc}",
        )
