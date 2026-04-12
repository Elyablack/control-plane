from __future__ import annotations

from .admin import analyze_admin_host_audit, run_admin_host_audit, verify_admin_host_audit
from .backup import run_backup, verify_backup
from .email import notify_email
from .mac import enqueue_mac_action
from .notify import notify_tg
from .types import ActionResult
from .weekly_review import generate_weekly_ops_review

ACTION_HANDLERS: dict[str, callable] = {
    "run_backup": run_backup,
    "verify_backup": verify_backup,
    "notify_tg": notify_tg,
    "notify_email": notify_email,
    "enqueue_mac_action": enqueue_mac_action,
    "run_admin_host_audit": run_admin_host_audit,
    "verify_admin_host_audit": verify_admin_host_audit,
    "analyze_admin_host_audit": analyze_admin_host_audit,
    "generate_weekly_ops_review": generate_weekly_ops_review,
}
