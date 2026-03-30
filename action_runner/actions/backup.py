from __future__ import annotations

import subprocess
from typing import Any


def run_backup(_: dict[str, Any]) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["/srv/control-plane/backup/run_backup.sh"],
        capture_output=True,
        text=True,
    )


def verify_backup(_: dict[str, Any]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            "bash",
            "-c",
            "ls -t /srv/backups/vps-backup-*.tar.gz | head -n1"
        ],
        capture_output=True,
        text=True,
    )
