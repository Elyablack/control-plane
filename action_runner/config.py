from __future__ import annotations

from pathlib import Path

BASE_DIR = Path("/srv/control-plane")
STATE_DIR = BASE_DIR / "state"
DB_PATH = STATE_DIR / "action_runner.db"

HOST = "0.0.0.0"
PORT = 8088

ALLOWED_ACTIONS = {
    "run_backup",
}

BACKUP_SCRIPT = "/srv/control-plane/backup/run_backup.sh"
