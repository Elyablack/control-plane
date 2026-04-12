from __future__ import annotations

from .admin import analyze_admin_host_audit, run_admin_host_audit, verify_admin_host_audit
from .backup import run_backup, verify_backup
from .email import notify_email
from .mac import enqueue_mac_action
from .mac_file import copy_file_to_mac
from .notify import notify_tg
from .types import ActionResult
from .vps import analyze_vps_host_audit, run_vps_host_audit, verify_vps_host_audit
from .weekly_review import generate_weekly_ops_review

ACTION_HANDLERS = {
    "run_backup": run_backup,
    "verify_backup": verify_backup,
    "notify_tg": notify_tg,
    "notify_email": notify_email,
    "enqueue_mac_action": enqueue_mac_action,
    "run_admin_host_audit": run_admin_host_audit,
    "verify_admin_host_audit": verify_admin_host_audit,
    "analyze_admin_host_audit": analyze_admin_host_audit,
    "generate_weekly_ops_review": generate_weekly_ops_review,
    "copy_file_to_mac": copy_file_to_mac,
    "run_vps_host_audit": run_vps_host_audit,
    "verify_vps_host_audit": verify_vps_host_audit,
    "analyze_vps_host_audit": analyze_vps_host_audit,
}
