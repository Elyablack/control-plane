from .backup import run_backup, verify_backup
from .notify import notify

ACTION_HANDLERS = {
    "run_backup": run_backup,
    "verify_backup": verify_backup,
    "notify": notify,
}
