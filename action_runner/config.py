from __future__ import annotations

from pathlib import Path

BASE_DIR = Path("/srv/control-plane")
STATE_DIR = BASE_DIR / "state"
DB_PATH = STATE_DIR / "action_runner.db"
RULES_PATH = BASE_DIR / "action_runner" / "rules.yaml"

HOST = "0.0.0.0"
PORT = 8088

ALLOWED_ACTIONS = {
    "run_backup",
    "verify_backup",
    "notify",
}
