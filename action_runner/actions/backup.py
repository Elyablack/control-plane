from __future__ import annotations

import subprocess
from typing import Any

from ..config import BACKUP_SCRIPT


def run_backup(_: dict[str, Any]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [BACKUP_SCRIPT],
        capture_output=True,
        text=True,
        check=False,
    )


def verify_backup(_: dict[str, Any]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "bash",
            "-c",
            "ls -t /srv/backups/vps-backup-*.tar.gz 2>/dev/null | head -n1",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
