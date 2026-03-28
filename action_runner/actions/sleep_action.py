from __future__ import annotations

import subprocess
from typing import Any


def sleep_action(payload: dict[str, Any]) -> subprocess.CompletedProcess[str]:
    seconds = int(payload.get("seconds", 10))
    return subprocess.run(
        ["sleep", str(seconds)],
        capture_output=True,
        text=True,
        check=False,
    )
