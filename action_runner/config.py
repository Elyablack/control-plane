from __future__ import annotations

import os
from pathlib import Path


def _env_str(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be int, got {raw!r}") from exc


BASE_DIR = Path(_env_str("CONTROL_PLANE_BASE_DIR", "/srv/control-plane"))
STATE_DIR = BASE_DIR / "state"
DB_PATH = STATE_DIR / "action_runner.db"
RULES_PATH = BASE_DIR / "action_runner" / "rules.yaml"
SCHEDULES_PATH = BASE_DIR / "action_runner" / "schedules.yaml"

HOST = _env_str("ACTION_RUNNER_HOST", "0.0.0.0")
PORT = _env_int("ACTION_RUNNER_PORT", 8088)

ALLOWED_ACTIONS = {
    "run_backup",
    "verify_backup",
    "notify_tg",
    "notify_email",
    "enqueue_mac_action",
    "run_admin_host_audit",
    "verify_admin_host_audit",
    "analyze_admin_host_audit",
    "run_vps_host_audit",
    "verify_vps_host_audit",
    "analyze_vps_host_audit",
    "run_monitoring_stack_audit",
    "verify_monitoring_stack_audit",
    "analyze_monitoring_stack_audit",
    "verify_mac_host_audit",
    "analyze_mac_host_audit",
    "generate_weekly_ops_review",
    "generate_ai_ops_brief",
    "copy_file_to_mac",
}

BACKUP_SCRIPT = _env_str("BACKUP_SCRIPT", "/srv/control-plane/backup/run_backup.sh")
TG_RELAY_URL = _env_str("TG_RELAY_URL", "http://127.0.0.1:8082/").rstrip("/") + "/"
TG_RELAY_TIMEOUT_SECONDS = _env_int("TG_RELAY_TIMEOUT_SECONDS", 11)

RESEND_API_KEY = _env_str("RESEND_API_KEY")
RESEND_FROM = _env_str("RESEND_FROM", "onboarding@resend.dev")
RESEND_TO = _env_str("RESEND_TO", "delivered@resend.dev")
RESEND_API_URL = _env_str("RESEND_API_URL", "https://api.resend.com/emails")
RESEND_TIMEOUT_SECONDS = _env_int("RESEND_TIMEOUT_SECONDS", 15)

OPENAI_API_KEY = _env_str("OPENAI_API_KEY")
OPENAI_BASE_URL = _env_str("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
OPENAI_WEEKLY_REVIEW_MODEL = _env_str("OPENAI_WEEKLY_REVIEW_MODEL", "gpt-5.4-nano")
OPENAI_OPS_BRIEF_MODEL = _env_str("OPENAI_OPS_BRIEF_MODEL", OPENAI_WEEKLY_REVIEW_MODEL)

MAC_REVIEW_SSH_TARGET = _env_str("MAC_REVIEW_SSH_TARGET", "mac")
MAC_REVIEW_DOCS_DIR = _env_str("MAC_REVIEW_DOCS_DIR", "~/Documents/control-plane-reviews")
MAC_REVIEW_COPY_TIMEOUT_SECONDS = _env_int("MAC_REVIEW_COPY_TIMEOUT_SECONDS", 30)

VPS_HOST_AUDIT_SCRIPT = _env_str("VPS_HOST_AUDIT_SCRIPT", "/usr/local/bin/vps_host_audit.sh")
VPS_HOST_AUDIT_LOG_DIR = _env_str("VPS_HOST_AUDIT_LOG_DIR", "/var/log/vps-host-audit")
VPS_HOST_AUDIT_METRICS_PATH = _env_str(
    "VPS_HOST_AUDIT_METRICS_PATH",
    "/var/lib/node_exporter/textfile_collector/vps_host_audit.prom",
)

MONITORING_STACK_AUDIT_LOG_DIR = _env_str(
    "MONITORING_STACK_AUDIT_LOG_DIR",
    "/var/log/monitoring-stack-audit",
)
MONITORING_STACK_AUDIT_METRICS_PATH = _env_str(
    "MONITORING_STACK_AUDIT_METRICS_PATH",
    "/var/lib/node_exporter/textfile_collector/monitoring_stack_audit.prom",
)
MONITORING_STACK_AUDIT_PROMETHEUS_URL = _env_str(
    "MONITORING_STACK_AUDIT_PROMETHEUS_URL",
    "http://127.0.0.1:9090",
)

DEFAULT_TASK_PRIORITY = 50
TASK_PRIORITY_BY_SEVERITY = {
    "critical": 100,
    "warning": 70,
    "info": 50,
    "test": 10,
}
