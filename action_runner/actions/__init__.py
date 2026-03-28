from .backup import run_backup
from .sleep_action import sleep_action

ACTION_HANDLERS = {
    "run_backup": run_backup,
    "sleep_action": sleep_action,
}
