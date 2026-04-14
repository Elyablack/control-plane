from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from ..mac_host_audit import (
    DEFAULT_MAC_AUDIT_DIR,
    analyze_mac_host_audit_snapshot,
    latest_mac_host_audit_path,
    load_mac_host_audit_snapshot,
)
from ..mac_host_audit_metrics import DEFAULT_MAC_HOST_AUDIT_METRICS_PATH, write_mac_host_audit_metrics
from .types import ActionResult


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def verify_mac_host_audit(payload: dict[str, Any]) -> ActionResult:
    audit_dir = str(payload.get("audit_dir", DEFAULT_MAC_AUDIT_DIR)).strip() or DEFAULT_MAC_AUDIT_DIR
    max_age_seconds = _safe_int(payload.get("max_age_seconds"), 1800)

    log_path = latest_mac_host_audit_path(audit_dir=audit_dir)
    if not log_path:
        return ActionResult(
            status="failed",
            exit_code=1,
            stdout="host=mac audit_verify=failed",
            stderr="",
            error=f"no mac host audit snapshot found in {audit_dir}",
        )

    path = Path(log_path)
    age_seconds = int(time.time() - path.stat().st_mtime)

    if age_seconds > max_age_seconds:
        return ActionResult(
            status="failed",
            exit_code=2,
            stdout=f"host=mac audit_verify=failed log_path={log_path} age_seconds={age_seconds}",
            stderr="",
            error=f"mac host audit snapshot too old: {age_seconds}s",
        )

    return ActionResult(
        status="success",
        exit_code=0,
        stdout=f"host=mac audit_verify=ok log_path={log_path} age_seconds={age_seconds}",
        stderr="",
        error=None,
    )


def analyze_mac_host_audit(payload: dict[str, Any]) -> ActionResult:
    audit_dir = str(payload.get("audit_dir", DEFAULT_MAC_AUDIT_DIR)).strip() or DEFAULT_MAC_AUDIT_DIR
    metrics_path = (
        str(payload.get("metrics_path", DEFAULT_MAC_HOST_AUDIT_METRICS_PATH)).strip()
        or DEFAULT_MAC_HOST_AUDIT_METRICS_PATH
    )

    log_path = latest_mac_host_audit_path(audit_dir=audit_dir)
    if not log_path:
        return ActionResult(
            status="failed",
            exit_code=1,
            stdout="",
            stderr="",
            error=f"no mac host audit snapshot found in {audit_dir}",
        )

    try:
        snapshot = load_mac_host_audit_snapshot(log_path)
        analysis = analyze_mac_host_audit_snapshot(snapshot, log_path=log_path)
        write_mac_host_audit_metrics(snapshot, analysis, metrics_path=metrics_path)
    except Exception as exc:
        return ActionResult(
            status="failed",
            exit_code=1,
            stdout="",
            stderr="",
            error=f"failed to analyze mac host audit: {exc}",
        )

    result_json = {
        "analysis_findings_count": len(analysis.findings),
        "analysis_level": analysis.level,
        "analysis_log_path": analysis.log_path,
        "analysis_summary": analysis.summary,
        "metrics_path": metrics_path,
    }

    stdout = (
        f"host=mac audit_analyze={analysis.level} findings={len(analysis.findings)} "
        f"log_path={analysis.log_path} details={analysis.summary} metrics_path={metrics_path}\n"
        f"RESULT_JSON:{json.dumps(result_json, ensure_ascii=False, sort_keys=True)}"
    )

    return ActionResult(
        status="success",
        exit_code=0,
        stdout=stdout,
        stderr="",
        error=None,
    )
