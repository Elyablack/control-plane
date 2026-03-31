from __future__ import annotations

import subprocess
from typing import Any

from ..config import BACKUP_SCRIPT
from .types import ActionResult, from_completed_process

RUN_BACKUP_EXIT_BLOCKED = 10
RUN_BACKUP_EXIT_SKIPPED = 11


def run_backup(_: dict[str, Any]) -> ActionResult:
    proc = subprocess.run(
        [BACKUP_SCRIPT],
        capture_output=True,
        text=True,
        check=False,
    )

    if proc.returncode == RUN_BACKUP_EXIT_BLOCKED:
        return ActionResult(
            status="blocked",
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            error="backup job is already running",
        )

    if proc.returncode == RUN_BACKUP_EXIT_SKIPPED:
        return ActionResult(
            status="skipped",
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            error="backup already completed today",
        )

    return from_completed_process(proc)


def verify_backup(_: dict[str, Any]) -> ActionResult:
    proc = subprocess.run(
        [
            "bash",
            "-c",
            "ls -t /srv/backups/vps-backup-*.tar.gz 2>/dev/null | head -n1",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return from_completed_process(proc)

