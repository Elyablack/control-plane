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


def ssh_run(
    host: str,
    command: str,
    *,
    timeout_seconds: int = DEFAULT_SSH_TIMEOUT_SECONDS,
    ssh_binary: str = "ssh",
    ssh_options: Sequence[str] = DEFAULT_SSH_OPTIONS,
) -> ActionResult:
    """
    Run a command on a remote host over SSH and normalize the result.

    This is a low-level execution tool.
    Domain-specific logic belongs in action handlers, not here.
    """
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
