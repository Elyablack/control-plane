from __future__ import annotations

import subprocess
from typing import Any


def notify(payload: dict[str, Any]) -> subprocess.CompletedProcess:
    message = payload.get("message", "no message")

    return subprocess.run(
        ["bash", "-c", f"echo '[NOTIFY] {message}'"],
        capture_output=True,
        text=True,
    )
