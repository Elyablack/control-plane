from __future__ import annotations

import subprocess
from typing import Any

from ..config import BACKUP_SCRIPT


def run_backup(payload: dict[str, Any]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [BACKUP_SCRIPT],
        capture_output=True,
        text=True,
        check=False,
    )
