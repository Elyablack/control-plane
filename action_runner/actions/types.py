from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional


ActionStatus = Literal["success", "failed", "blocked", "skipped"]


@dataclass(slots=True)
class ActionResult:
    status: ActionStatus
    exit_code: Optional[int]
    stdout: str
    stderr: str
    error: str | None = None


def from_completed_process(proc) -> ActionResult:
    return ActionResult(
        status="success" if proc.returncode == 0 else "failed",
        exit_code=proc.returncode,
        stdout=proc.stdout,
        stderr=proc.stderr,
        error=None if proc.returncode == 0 else f"command exited with code {proc.returncode}",
    )

