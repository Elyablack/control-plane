from __future__ import annotations

import os
import posixpath
import shlex
from pathlib import Path
from typing import Any

from ..config import (
    MAC_REVIEW_COPY_TIMEOUT_SECONDS,
    MAC_REVIEW_DOCS_DIR,
    MAC_REVIEW_SSH_TARGET,
)
from ..tools import scp_copy_to_remote, ssh_run
from .types import ActionResult


def _as_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def _expand_remote_dir(value: str) -> str:
    if value == "~":
        return "$HOME"
    if value.startswith("~/"):
        suffix = value[2:]
        return f"$HOME/{suffix}" if suffix else "$HOME"
    return value


def copy_file_to_mac(payload: dict[str, Any]) -> ActionResult:
    source_path = _as_str(payload.get("source_path"))
    if not source_path:
        return ActionResult(
            status="failed",
            exit_code=1,
            stdout="",
            stderr="",
            error="payload.source_path is required",
        )

    local_path = Path(source_path)
    if not local_path.is_file():
        return ActionResult(
            status="failed",
            exit_code=1,
            stdout="",
            stderr="",
            error=f"source file not found: {source_path}",
        )

    ssh_target = _as_str(payload.get("ssh_target"), MAC_REVIEW_SSH_TARGET)
    target_dir_raw = _as_str(payload.get("target_dir"), MAC_REVIEW_DOCS_DIR)
    target_dir_shell = _expand_remote_dir(target_dir_raw)
    timeout_seconds_raw = payload.get("timeout_seconds", MAC_REVIEW_COPY_TIMEOUT_SECONDS)
    filename = _as_str(payload.get("filename"), local_path.name)

    try:
        timeout_seconds = int(timeout_seconds_raw)
    except (TypeError, ValueError):
        return ActionResult(
            status="failed",
            exit_code=1,
            stdout="",
            stderr="",
            error=f"invalid timeout_seconds: {timeout_seconds_raw!r}",
        )

    if timeout_seconds <= 0:
        return ActionResult(
            status="failed",
            exit_code=1,
            stdout="",
            stderr="",
            error="timeout_seconds must be > 0",
        )

    mkdir_result = ssh_run(
        host=ssh_target,
        command=f"mkdir -p {shlex.quote(target_dir_shell)}",
        timeout_seconds=timeout_seconds,
    )
    if mkdir_result.status != "success":
        return ActionResult(
            status="failed",
            exit_code=mkdir_result.exit_code,
            stdout="",
            stderr=mkdir_result.stderr,
            error=mkdir_result.error or "failed to create remote directory",
        )

    remote_path = posixpath.join(target_dir_raw.rstrip("/"), filename)
    scp_result = scp_copy_to_remote(
        local_path=str(local_path),
        remote_host=ssh_target,
        remote_path=remote_path,
        timeout_seconds=timeout_seconds,
    )
    if scp_result.status != "success":
        return ActionResult(
            status="failed",
            exit_code=scp_result.exit_code,
            stdout="",
            stderr=scp_result.stderr,
            error=scp_result.error or "failed to copy file to mac",
        )

    return ActionResult(
        status="success",
        exit_code=0,
        stdout=(
            f"copy_to_mac=ok source_path={source_path} "
            f"remote_host={ssh_target} remote_path={remote_path}"
        ),
        stderr="",
        error=None,
    )

