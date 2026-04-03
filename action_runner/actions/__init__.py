from .backup import run_backup, verify_backup
from .notify import notify_tg
from .mac import enqueue_mac_action

ACTION_HANDLERS = {
    "run_backup": run_backup,
    "verify_backup": verify_backup,
    "notify_tg": notify_tg,
    "enqueue_mac_action": enqueue_mac_action,
}
