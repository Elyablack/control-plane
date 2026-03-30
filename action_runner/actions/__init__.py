from .backup import run_backup, verify_backup
from .notify import notify_tg

ACTION_HANDLERS = {
    "run_backup": run_backup,
    "verify_backup": verify_backup,
    "notify_tg": notify_tg,
}
