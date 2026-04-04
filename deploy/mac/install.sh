#!/usr/bin/env bash
set -Eeuo pipefail

MAC_HOST="${MAC_HOST:-elvira@Elvira}"
MAC_BASE_DIR="${MAC_BASE_DIR:-/Users/elvira/scripts}"
MAC_APP_DIR="${MAC_APP_DIR:-${MAC_BASE_DIR}/mac_memory_guard}"
MAC_LAUNCH_AGENTS_DIR="${MAC_LAUNCH_AGENTS_DIR:-/Users/elvira/Library/LaunchAgents}"
MAC_LOG_DIR="${MAC_LOG_DIR:-/Users/elvira/logs}"

OLD_PLIST_NAME="com.elvira.mac-memory-guard.plist"
OLD_LABEL="com.elvira.mac-memory-guard"

REPORT_PLIST_NAME="com.elvira.mac-memory-report.plist"
REPORT_LABEL="com.elvira.mac-memory-report"

WORKER_PLIST_NAME="com.elvira.mac-memory-worker.plist"
WORKER_LABEL="com.elvira.mac-memory-worker"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
AGENT_SRC_DIR="${REPO_ROOT}/agents/mac_memory_guard"
REPORT_PLIST_SRC="${REPO_ROOT}/deploy/mac/${REPORT_PLIST_NAME}"
WORKER_PLIST_SRC="${REPO_ROOT}/deploy/mac/${WORKER_PLIST_NAME}"

echo "[deploy] repo root: ${REPO_ROOT}"
echo "[deploy] mac host: ${MAC_HOST}"

if [[ ! -d "${AGENT_SRC_DIR}" ]]; then
  echo "[deploy] missing agent dir: ${AGENT_SRC_DIR}" >&2
  exit 1
fi

if [[ ! -f "${REPORT_PLIST_SRC}" ]]; then
  echo "[deploy] missing report plist: ${REPORT_PLIST_SRC}" >&2
  exit 1
fi

if [[ ! -f "${WORKER_PLIST_SRC}" ]]; then
  echo "[deploy] missing worker plist: ${WORKER_PLIST_SRC}" >&2
  exit 1
fi

echo "[deploy] pre-create remote dirs"
ssh "${MAC_HOST}" "mkdir -p '${MAC_BASE_DIR}' '${MAC_APP_DIR}' '${MAC_LAUNCH_AGENTS_DIR}' '${MAC_LOG_DIR}'"

echo "[deploy] sync mac agent"
rsync -av --delete \
  --exclude '__pycache__/' \
  --exclude '*.pyc' \
  "${AGENT_SRC_DIR}/" \
  "${MAC_HOST}:${MAC_APP_DIR}/"

echo "[deploy] install plists"
scp "${REPORT_PLIST_SRC}" "${MAC_HOST}:${MAC_LAUNCH_AGENTS_DIR}/${REPORT_PLIST_NAME}"
scp "${WORKER_PLIST_SRC}" "${MAC_HOST}:${MAC_LAUNCH_AGENTS_DIR}/${WORKER_PLIST_NAME}"

echo "[deploy] cleanup legacy files"
ssh "${MAC_HOST}" "
  rm -f '${MAC_BASE_DIR}/mac_memory_guard.py' &&
  rm -rf '${MAC_APP_DIR}/__pycache__' &&
  rm -f '${MAC_LAUNCH_AGENTS_DIR}/${OLD_PLIST_NAME}'
"

echo "[deploy] validate python syntax on mac"
ssh "${MAC_HOST}" "
  cd '${MAC_BASE_DIR}' &&
  python3 -m py_compile mac_memory_guard/*.py
"

echo "[deploy] reload launchd jobs"
ssh "${MAC_HOST}" "
  launchctl bootout gui/\$(id -u) '${MAC_LAUNCH_AGENTS_DIR}/${OLD_PLIST_NAME}' >/dev/null 2>&1 || true
  launchctl disable gui/\$(id -u)/${OLD_LABEL} >/dev/null 2>&1 || true

  launchctl bootout gui/\$(id -u) '${MAC_LAUNCH_AGENTS_DIR}/${REPORT_PLIST_NAME}' >/dev/null 2>&1 || true
  launchctl bootout gui/\$(id -u) '${MAC_LAUNCH_AGENTS_DIR}/${WORKER_PLIST_NAME}' >/dev/null 2>&1 || true

  launchctl bootstrap gui/\$(id -u) '${MAC_LAUNCH_AGENTS_DIR}/${REPORT_PLIST_NAME}'
  launchctl bootstrap gui/\$(id -u) '${MAC_LAUNCH_AGENTS_DIR}/${WORKER_PLIST_NAME}'

  launchctl enable gui/\$(id -u)/${REPORT_LABEL}
  launchctl enable gui/\$(id -u)/${WORKER_LABEL}

  launchctl kickstart -k gui/\$(id -u)/${REPORT_LABEL}
  launchctl kickstart -k gui/\$(id -u)/${WORKER_LABEL}
"

echo "[deploy] status"
ssh "${MAC_HOST}" "
  echo '--- report ---'
  launchctl print gui/\$(id -u)/${REPORT_LABEL} | sed -n '1,60p'
  echo
  echo '--- worker ---'
  launchctl print gui/\$(id -u)/${WORKER_LABEL} | sed -n '1,60p'
"

echo "[deploy] tail logs"
ssh "${MAC_HOST}" "
  echo '--- mac_memory_guard.log ---'
  tail -n 20 '${MAC_LOG_DIR}/mac_memory_guard.log' 2>/dev/null || true
  echo
  echo '--- mac_report.err.log ---'
  tail -n 20 '${MAC_LOG_DIR}/mac_report.err.log' 2>/dev/null || true
  echo
  echo '--- mac_worker.err.log ---'
  tail -n 20 '${MAC_LOG_DIR}/mac_worker.err.log' 2>/dev/null || true
"

echo "[deploy] done"
