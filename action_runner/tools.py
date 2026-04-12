from __future__ import annotations

import shlex
import subprocess
from typing import Sequence

from .actions.types import ActionResult, from_completed_process

DEFAULT_SSH_TIMEOUT_SECONDS = 30
DEFAULT_SSH_OPTIONS: tuple[str, ...] = (
    "-o",
    "BatchMode=yes",
    "-o",
    "StrictHostKeyChecking=accept-new",
    "-o",
    "ConnectTimeout=10",
)


def _build_ssh_command(
    host: str,
    command: str,
    *,
    ssh_binary: str = "ssh",
    ssh_options: Sequence[str] = DEFAULT_SSH_OPTIONS,
) -> list[str]:
    normalized_host = host.strip()
    normalized_command = command.strip()

    if not normalized_host:
        raise ValueError("host is required")
    if not normalized_command:
        raise ValueError("command is required")

    return [
        ssh_binary,
        *ssh_options,
        normalized_host,
        normalized_command,
    ]


def _build_scp_command(
    local_path: str,
    remote_host: str,
    remote_path: str,
    *,
    scp_binary: str = "scp",
    ssh_options: Sequence[str] = DEFAULT_SSH_OPTIONS,
) -> list[str]:
    normalized_local_path = local_path.strip()
    normalized_remote_host = remote_host.strip()
    normalized_remote_path = remote_path.strip()

    if not normalized_local_path:
        raise ValueError("local_path is required")
    if not normalized_remote_host:
        raise ValueError("remote_host is required")
    if not normalized_remote_path:
        raise ValueError("remote_path is required")

    return [
        scp_binary,
        *ssh_options,
        normalized_local_path,
        f"{normalized_remote_host}:{normalized_remote_path}",
    ]


def ssh_run(
    host: str,
    command: str,
    *,
    timeout_seconds: int = DEFAULT_SSH_TIMEOUT_SECONDS,
    ssh_binary: str = "ssh",
    ssh_options: Sequence[str] = DEFAULT_SSH_OPTIONS,
) -> ActionResult:
    try:
        argv = _build_ssh_command(
            host,
            command,
            ssh_binary=ssh_binary,
            ssh_options=ssh_options,
        )
    except ValueError as exc:
        return ActionResult(
            status="failed",
            exit_code=1,
            stdout="",
            stderr="",
            error=str(exc),
        )

    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_seconds,
        )
        return from_completed_process(proc)
    except subprocess.TimeoutExpired as exc:
        return ActionResult(
            status="failed",
            exit_code=124,
            stdout=exc.stdout or "",
            stderr=exc.stderr or "",
            error=f"ssh command timed out after {timeout_seconds}s",
        )
    except Exception as exc:
        safe_cmd = " ".join(shlex.quote(part) for part in argv)
        return ActionResult(
            status="failed",
            exit_code=1,
            stdout="",
            stderr="",
            error=f"ssh execution failed: {exc}; argv={safe_cmd}",
        )


def scp_copy_to_remote(
    local_path: str,
    remote_host: str,
    remote_path: str,
    *,
    timeout_seconds: int = DEFAULT_SSH_TIMEOUT_SECONDS,
    scp_binary: str = "scp",
    ssh_options: Sequence[str] = DEFAULT_SSH_OPTIONS,
) -> ActionResult:
    try:
        argv = _build_scp_command(
            local_path,
            remote_host,
            remote_path,
            scp_binary=scp_binary,
            ssh_options=ssh_options,
        )
    except ValueError as exc:
        return ActionResult(
            status="failed",
            exit_code=1,
            stdout="",
            stderr="",
            error=str(exc),
        )

    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_seconds,
        )
        return from_completed_process(proc)
    except subprocess.TimeoutExpired as exc:
        return ActionResult(
            status="failed",
            exit_code=124,
            stdout=exc.stdout or "",
            stderr=exc.stderr or "",
            error=f"scp command timed out after {timeout_seconds}s",
        )
    except Exception as exc:
        safe_cmd = " ".join(shlex.quote(part) for part in argv)
        return ActionResult(
            status="failed",
            exit_code=1,
            stdout="",
            stderr="",
            error=f"scp execution failed: {exc}; argv={safe_cmd}",
        )

