from __future__ import annotations

import json
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from ..config import (
    MONITORING_STACK_AUDIT_LOG_DIR,
    MONITORING_STACK_AUDIT_METRICS_PATH,
    MONITORING_STACK_AUDIT_PROMETHEUS_URL,
)
from ..monitoring_stack_audit import (
    analyze_monitoring_stack_audit_log,
    parse_monitoring_stack_audit_log,
    render_monitoring_stack_audit_metrics,
)
from .types import ActionResult

DEFAULT_LOG_DIR = MONITORING_STACK_AUDIT_LOG_DIR
DEFAULT_METRICS_PATH = MONITORING_STACK_AUDIT_METRICS_PATH
DEFAULT_MAX_AGE_SECONDS = 1800
DEFAULT_RUN_TIMEOUT_SECONDS = 60
DEFAULT_HTTP_TIMEOUT_SECONDS = 5
DEFAULT_PROMETHEUS_BASE_URL = MONITORING_STACK_AUDIT_PROMETHEUS_URL

CONTAINERS: tuple[tuple[str, str], ...] = (
    ("prometheus", "prometheus"),
    ("alertmanager", "alertmanager"),
    ("grafana", "grafana"),
    ("loki", "loki"),
    ("promtail", "promtail"),
    ("tg-relay", "tg_relay"),
    ("demo-app", "demo_app"),
)

PROBES: tuple[tuple[str, str], ...] = (
    ("probe_prometheus_ready", "http://127.0.0.1:9090/-/ready"),
    ("probe_alertmanager_ready", "http://127.0.0.1:9093/-/ready"),
    ("probe_grafana_health", "http://127.0.0.1:3000/api/health"),
    ("probe_loki_ready", "http://127.0.0.1:3100/ready"),
    ("probe_promtail_ready", "http://127.0.0.1:9080/ready"),
    ("probe_tg_relay_ready", "http://127.0.0.1:8082/readyz"),
    ("probe_demo_app_health", "http://127.0.0.1:8081/healthz"),
)

PROM_QUERIES: tuple[tuple[str, str], ...] = (
    ("prometheus_target_nodes_vps_up", 'max(up{job="nodes",node="vps"})'),
    ("prometheus_target_nodes_admin_up", 'max(up{job="nodes",node="admin"})'),
    ("prometheus_target_action_runner_up", 'max(up{job="action-runner"})'),
    ("prometheus_target_demo_app_up", 'max(up{job="demo-app"})'),
    (
        "demo_app_5xx_rate",
        'sum(rate(http_requests_total{service="demo-app",status=~"5.."}[2m]))',
    ),
    (
        "demo_app_p95_latency_seconds",
        """
        histogram_quantile(
          0.95,
          sum by (le) (
            rate(http_request_duration_seconds_bucket{service="demo-app"}[5m])
          )
        )
        """,
    ),
    ("prometheus_up_zero_count", "count(up == 0)"),
)

REQUIRED_VERIFY_KEYS = (
    "container_prometheus_exists",
    "container_alertmanager_exists",
    "container_grafana_exists",
    "container_loki_exists",
    "container_promtail_exists",
    "container_tg_relay_exists",
    "container_demo_app_exists",
    "probe_prometheus_ready",
    "probe_alertmanager_ready",
    "probe_grafana_health",
    "probe_loki_ready",
    "probe_promtail_ready",
    "probe_tg_relay_ready",
    "probe_demo_app_health",
    "prometheus_query_api",
    "prometheus_target_nodes_vps_up",
    "prometheus_target_nodes_admin_up",
    "prometheus_target_action_runner_up",
    "prometheus_target_demo_app_up",
    "prometheus_required_targets_down",
    "prometheus_total_targets_down",
)


def _as_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _latest_audit_log(log_dir: str) -> Path | None:
    target_dir = Path(log_dir)
    if not target_dir.exists():
        return None
    files = sorted(target_dir.glob("audit_*.log"), key=lambda path: path.stat().st_mtime, reverse=True)
    return files[0] if files else None


def _http_probe(url: str, *, timeout_seconds: int) -> str:
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
            return "ok" if 200 <= resp.status < 300 else f"http_{resp.status}"
    except Exception:
        return "failed"


def _prom_query(base_url: str, query: str, *, timeout_seconds: int) -> tuple[str, float | None]:
    url = f"{base_url.rstrip('/')}/api/v1/query?{urllib.parse.urlencode({'query': query})}"
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError):
        return "failed", None

    if payload.get("status") != "success":
        return "failed", None

    result = payload.get("data", {}).get("result", [])
    if not isinstance(result, list) or not result:
        return "ok", None

    first = result[0]
    if not isinstance(first, dict):
        return "ok", None

    value = first.get("value")
    if not isinstance(value, list) or len(value) < 2:
        return "ok", None

    try:
        return "ok", float(value[1])
    except (TypeError, ValueError):
        return "ok", None


def _docker_inspect_container(container_name: str, *, timeout_seconds: int) -> dict[str, str]:
    argv = ["docker", "inspect", container_name]

    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except Exception as exc:
        return {
            "exists": "unknown",
            "state": "unknown",
            "health": "unknown",
            "image": "",
            "status": "inspect_failed",
            "error": str(exc),
        }

    stderr_text = (proc.stderr or "").strip().lower()

    if proc.returncode != 0:
        if "no such object" in stderr_text or "no such container" in stderr_text:
            return {
                "exists": "no",
                "state": "missing",
                "health": "unknown",
                "image": "",
                "status": "missing",
                "error": (proc.stderr or "").strip(),
            }
        return {
            "exists": "unknown",
            "state": "unknown",
            "health": "unknown",
            "image": "",
            "status": "inspect_failed",
            "error": (proc.stderr or "").strip() or "docker inspect failed",
        }

    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        return {
            "exists": "unknown",
            "state": "unknown",
            "health": "unknown",
            "image": "",
            "status": "inspect_failed",
            "error": f"invalid docker inspect json: {exc}",
        }

    if not isinstance(payload, list) or not payload or not isinstance(payload[0], dict):
        return {
            "exists": "unknown",
            "state": "unknown",
            "health": "unknown",
            "image": "",
            "status": "inspect_failed",
            "error": "docker inspect returned unexpected payload",
        }

    item = payload[0]
    state_obj = item.get("State") if isinstance(item.get("State"), dict) else {}
    config_obj = item.get("Config") if isinstance(item.get("Config"), dict) else {}
    health_obj = state_obj.get("Health") if isinstance(state_obj.get("Health"), dict) else {}

    return {
        "exists": "yes",
        "state": str(state_obj.get("Status", "unknown") or "unknown"),
        "health": str(health_obj.get("Status", "none") or "none"),
        "image": str(config_obj.get("Image", "") or ""),
        "status": str(state_obj.get("Status", "unknown") or "unknown"),
        "error": "",
    }


def _containers_restarting_total(container_data: dict[str, dict[str, str]]) -> int:
    return sum(1 for item in container_data.values() if item.get("state") == "restarting")


def run_monitoring_stack_audit(payload: dict[str, Any]) -> ActionResult:
    log_dir = _as_str(payload.get("log_dir"), DEFAULT_LOG_DIR)
    timeout_seconds = _as_int(payload.get("timeout_seconds"), DEFAULT_RUN_TIMEOUT_SECONDS)
    http_timeout_seconds = _as_int(payload.get("http_timeout_seconds"), DEFAULT_HTTP_TIMEOUT_SECONDS)
    prometheus_base_url = _as_str(payload.get("prometheus_base_url"), DEFAULT_PROMETHEUS_BASE_URL)

    if timeout_seconds <= 0:
        timeout_seconds = DEFAULT_RUN_TIMEOUT_SECONDS
    if http_timeout_seconds <= 0:
        http_timeout_seconds = DEFAULT_HTTP_TIMEOUT_SECONDS

    try:
        target_dir = Path(log_dir)
        target_dir.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        return ActionResult(
            status="failed",
            exit_code=1,
            stdout="",
            stderr="",
            error=f"failed to create monitoring stack audit log dir: {exc}",
        )

    stamp = time.strftime("%Y-%m-%d_%H-%M-%S", time.gmtime())
    log_path = target_dir / f"audit_{stamp}.log"

    container_data: dict[str, dict[str, str]] = {}
    for docker_name, key_name in CONTAINERS:
        container_data[key_name] = _docker_inspect_container(docker_name, timeout_seconds=timeout_seconds)

    probe_data = {key: _http_probe(url, timeout_seconds=http_timeout_seconds) for key, url in PROBES}

    prom_results: dict[str, float | None] = {}
    prom_api_status = "ok"
    for key, query in PROM_QUERIES:
        status, value = _prom_query(prometheus_base_url, query, timeout_seconds=http_timeout_seconds)
        if status != "ok":
            prom_api_status = "failed"
        prom_results[key] = value

    required_targets = {
        "nodes_vps": prom_results.get("prometheus_target_nodes_vps_up"),
        "nodes_admin": prom_results.get("prometheus_target_nodes_admin_up"),
        "action_runner": prom_results.get("prometheus_target_action_runner_up"),
    }
    required_targets_down = sum(1 for value in required_targets.values() if value is None or value < 1)
    total_targets_down = int(prom_results.get("prometheus_up_zero_count") or 0)

    lines = [
        "host=vps",
        "audit_type=monitoring_stack",
    ]

    for key_name, item in container_data.items():
        key_base = f"container_{key_name}"
        lines.append(f"{key_base}_exists={item['exists']}")
        lines.append(f"{key_base}_state={item['state']}")
        lines.append(f"{key_base}_health={item['health']}")
        lines.append(f"{key_base}_image={item['image']}")
        lines.append(f"{key_base}_status={item['status']}")
        lines.append(f"{key_base}_error={item.get('error', '')}")

    for key, value in probe_data.items():
        lines.append(f"{key}={value}")

    lines.append(f"prometheus_query_api={prom_api_status}")

    for key, value in prom_results.items():
        lines.append(f"{key}={'' if value is None else value}")

    lines.append(f"prometheus_required_targets_down={required_targets_down}")
    lines.append(f"prometheus_total_targets_down={total_targets_down}")
    lines.append(f"containers_restarting_total={_containers_restarting_total(container_data)}")

    try:
        log_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    except Exception as exc:
        return ActionResult(
            status="failed",
            exit_code=1,
            stdout="",
            stderr="",
            error=f"failed to write monitoring stack audit log: {exc}",
        )

    return ActionResult(
        status="success",
        exit_code=0,
        stdout=f"host=vps monitoring_stack_audit=completed log_path={log_path}",
        stderr="",
        error=None,
    )


def verify_monitoring_stack_audit(payload: dict[str, Any]) -> ActionResult:
    log_dir = _as_str(payload.get("log_dir"), DEFAULT_LOG_DIR)
    max_age_seconds = _as_int(payload.get("max_age_seconds"), DEFAULT_MAX_AGE_SECONDS)
    if max_age_seconds <= 0:
        max_age_seconds = DEFAULT_MAX_AGE_SECONDS

    log_path = _latest_audit_log(log_dir)
    if log_path is None:
        return ActionResult(
            status="failed",
            exit_code=11,
            stdout="host=vps monitoring_stack_audit_verify=failed",
            stderr="",
            error="no monitoring stack audit log found",
        )

    try:
        stat = log_path.stat()
    except Exception as exc:
        return ActionResult(
            status="failed",
            exit_code=12,
            stdout="host=vps monitoring_stack_audit_verify=failed",
            stderr="",
            error=f"failed to stat audit log: {exc}",
        )

    age_seconds = time.time() - stat.st_mtime
    if age_seconds > max_age_seconds:
        return ActionResult(
            status="failed",
            exit_code=13,
            stdout="host=vps monitoring_stack_audit_verify=failed",
            stderr="",
            error="latest monitoring stack audit log is too old",
        )

    try:
        parsed = parse_monitoring_stack_audit_log(str(log_path))
    except Exception as exc:
        return ActionResult(
            status="failed",
            exit_code=14,
            stdout="host=vps monitoring_stack_audit_verify=failed",
            stderr="",
            error=f"failed to parse audit log: {exc}",
        )

    missing_keys = [key for key in REQUIRED_VERIFY_KEYS if key not in parsed]
    if missing_keys:
        return ActionResult(
            status="failed",
            exit_code=15,
            stdout="host=vps monitoring_stack_audit_verify=failed",
            stderr="",
            error=f"monitoring stack audit log missing required keys: {', '.join(missing_keys)}",
        )

    return ActionResult(
        status="success",
        exit_code=0,
        stdout=f"host=vps monitoring_stack_audit_verify=ok log_path={log_path} age_seconds={int(age_seconds)}",
        stderr="",
        error=None,
    )


def analyze_monitoring_stack_audit(payload: dict[str, Any]) -> ActionResult:
    log_dir = _as_str(payload.get("log_dir"), DEFAULT_LOG_DIR)
    metrics_path = _as_str(payload.get("metrics_path"), DEFAULT_METRICS_PATH)

    log_path = _latest_audit_log(log_dir)
    if log_path is None:
        return ActionResult(
            status="failed",
            exit_code=11,
            stdout="",
            stderr="",
            error="no monitoring stack audit log found",
        )

    try:
        log_data = parse_monitoring_stack_audit_log(str(log_path))
        analysis = analyze_monitoring_stack_audit_log(str(log_path))
        metrics_text = render_monitoring_stack_audit_metrics(analysis, log_data=log_data, host="vps")
    except Exception as exc:
        return ActionResult(
            status="failed",
            exit_code=1,
            stdout="",
            stderr="",
            error=f"failed to analyze monitoring stack audit: {exc}",
        )

    metrics_file = Path(metrics_path)
    try:
        metrics_file.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = metrics_file.with_suffix(metrics_file.suffix + ".tmp")
        tmp_path.write_text(metrics_text, encoding="utf-8")
        tmp_path.replace(metrics_file)
    except Exception as exc:
        return ActionResult(
            status="failed",
            exit_code=1,
            stdout="",
            stderr="",
            error=f"failed to write monitoring stack audit metrics: {exc}",
        )

    result_payload = {
        "analysis_findings_count": len(analysis.findings),
        "analysis_level": analysis.level,
        "analysis_log_path": str(log_path),
        "analysis_summary": analysis.summary,
        "metrics_path": str(metrics_file),
    }

    stdout = (
        f"host=vps audit_analyze={analysis.level} findings={len(analysis.findings)} "
        f"log_path={log_path} details={analysis.summary} metrics_path={metrics_file}\n"
        f"RESULT_JSON:{json.dumps(result_payload, ensure_ascii=False, sort_keys=True)}"
    )

    return ActionResult(
        status="success",
        exit_code=0,
        stdout=stdout,
        stderr="",
        error=None,
    )
