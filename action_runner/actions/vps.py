from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any

from ..config import VPS_HOST_AUDIT_LOG_DIR, VPS_HOST_AUDIT_METRICS_PATH, VPS_HOST_AUDIT_SCRIPT
from ..vps_audit import analyze_vps_audit_log
from ..vps_audit_metrics import write_vps_audit_metrics
from .types import ActionResult


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _latest_log(log_dir: str) -> Path | None:
    path = Path(log_dir)
    if not path.exists():
        return None
    logs = sorted(path.glob("audit_*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
    return logs[0] if logs else None


def run_vps_host_audit(payload: dict[str, Any]) -> ActionResult:
    timeout_seconds = _as_int(payload.get("timeout_seconds"), 120)
    log_dir = str(payload.get("log_dir", VPS_HOST_AUDIT_LOG_DIR)).strip() or VPS_HOST_AUDIT_LOG_DIR

    try:
        proc = subprocess.run(
            ["bash", VPS_HOST_AUDIT_SCRIPT, log_dir],
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        return ActionResult(
            status="failed",
            exit_code=124,
            stdout=exc.stdout or "",
            stderr=exc.stderr or "",
            error=f"vps host audit timed out after {timeout_seconds}s",
        )
    except Exception as exc:
        return ActionResult(
            status="failed",
            exit_code=1,
            stdout="",
            stderr="",
            error=f"failed to execute vps host audit: {exc}",
        )

    status = "success" if proc.returncode == 0 else "failed"
    return ActionResult(
        status=status,
        exit_code=proc.returncode,
        stdout=proc.stdout,
        stderr=proc.stderr,
        error=None if proc.returncode == 0 else f"command exited with code {proc.returncode}",
    )


def verify_vps_host_audit(payload: dict[str, Any]) -> ActionResult:
    log_dir = str(payload.get("log_dir", VPS_HOST_AUDIT_LOG_DIR)).strip() or VPS_HOST_AUDIT_LOG_DIR
    max_age_seconds = _as_int(payload.get("max_age_seconds"), 1800)

    latest = _latest_log(log_dir)
    if latest is None:
        return ActionResult(
            status="failed",
            exit_code=10,
            stdout="",
            stderr="",
            error="no vps audit logs found",
        )

    age_seconds = int(time.time() - latest.stat().st_mtime)
    if age_seconds > max_age_seconds:
        return ActionResult(
            status="failed",
            exit_code=14,
            stdout="",
            stderr="",
            error="latest vps audit log is too old",
        )

    return ActionResult(
        status="success",
        exit_code=0,
        stdout=f"vps_host_audit_verify=ok log_path={latest} age_seconds={age_seconds}",
        stderr="",
        error=None,
    )


def analyze_vps_host_audit(payload: dict[str, Any]) -> ActionResult:
    log_dir = str(payload.get("log_dir", VPS_HOST_AUDIT_LOG_DIR)).strip() or VPS_HOST_AUDIT_LOG_DIR
    metrics_path = str(payload.get("metrics_path", VPS_HOST_AUDIT_METRICS_PATH)).strip() or VPS_HOST_AUDIT_METRICS_PATH

    latest = _latest_log(log_dir)
    if latest is None:
        return ActionResult(
            status="failed",
            exit_code=10,
            stdout="",
            stderr="",
            error="no vps audit logs found",
        )

    try:
        analysis = analyze_vps_audit_log(str(latest))
        written_metrics_path = write_vps_audit_metrics(analysis=analysis, metrics_path=metrics_path)
    except Exception as exc:
        return ActionResult(
            status="failed",
            exit_code=1,
            stdout="",
            stderr="",
            error=f"failed to analyze vps host audit: {exc}",
        )

    result_json = {
        "analysis_level": analysis.level,
        "analysis_findings_count": len(analysis.findings),
        "analysis_summary": analysis.summary,
        "analysis_log_path": str(latest),
        "metrics_path": written_metrics_path,
    }

    stdout = (
        f"host=vps audit_analyze={analysis.level} findings={len(analysis.findings)} "
        f"log_path={latest} details={analysis.summary} metrics_path={written_metrics_path}\n"
        f"RESULT_JSON:{json.dumps(result_json, ensure_ascii=False, sort_keys=True)}"
    )

    return ActionResult(
        status="success",
        exit_code=0,
        stdout=stdout,
        stderr="",
        error=None,
    )
