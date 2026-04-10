from __future__ import annotations

from pathlib import Path

BASE_DIR = Path("/srv/control-plane")
STATE_DIR = BASE_DIR / "state"
DB_PATH = STATE_DIR / "action_runner.db"
RULES_PATH = BASE_DIR / "action_runner" / "rules.yaml"
SCHEDULES_PATH = BASE_DIR / "action_runner" / "schedules.yaml"

HOST = "0.0.0.0"
PORT = 8088

ALLOWED_ACTIONS = {
    "run_backup",
    "verify_backup",
    "notify_tg",
    "enqueue_mac_action",
    "run_admin_host_audit",
    "verify_admin_host_audit",
}

BACKUP_SCRIPT = "/srv/control-plane/backup/run_backup.sh"
TG_RELAY_URL = "http://127.0.0.1:8082/"
TG_RELAY_TIMEOUT_SECONDS = 11

DEFAULT_TASK_PRIORITY = 50
TASK_PRIORITY_BY_SEVERITY = {
    "critical": 100,
    "warning": 700,
    "info": 50,
    "test": 10,
}
