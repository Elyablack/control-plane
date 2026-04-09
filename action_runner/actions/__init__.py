from __future__ import annotations

from typing import Any, Callable

from .admin import run_admin_host_audit, verify_admin_host_audit
from .backup import run_backup, verify_backup
from .notify import notify_tg
from .mac import enqueue_mac_action
from .types import ActionResult

ActionHandler = Callable[[dict[str, Any]], ActionResult]

ACTION_HANDLERS: dict[str, ActionHandler] = {
    "run_backup": run_backup,
    "verify_backup": verify_backup,
    "notify_tg": notify_tg,
    "enqueue_mac_action": enqueue_mac_action,
    "run_admin_host_audit": run_admin_host_audit,
    "verify_admin_host_audit": verify_admin_host_audit,
}
