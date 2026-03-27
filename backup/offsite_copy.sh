#!/usr/bin/env bash
set -Eeuo pipefail

BACKUP_DIR="/srv/backups"
TARGET_HOST="admin"
TARGET_DIR="/home/admin1/infra-backups"
LOG_FILE="${BACKUP_LOG_FILE:-/srv/control-plane/logs/backup.log}"
ERR_FILE="${BACKUP_ERR_FILE:-/srv/control-plane/logs/backup.err.log}"
CURRENT_STEP="offsite_copy"

timestamp() {
  date -u '+%Y-%m-%d %H:%M:%S UTC'
}

log() {
  local msg="$*"
  printf '[%s] INFO  [%s] %s\n' "$(timestamp)" "$CURRENT_STEP" "$msg" | tee -a "$LOG_FILE"
}

log_err() {
  local msg="$*"
  printf '[%s] ERROR [%s] %s\n' "$(timestamp)" "$CURRENT_STEP" "$msg" | tee -a "$ERR_FILE" >&2
}

on_error() {
  local exit_code=$?
  local line_no=${1:-unknown}
  log_err "failed with exit_code=${exit_code} at line=${line_no}"
  exit "$exit_code"
}

trap 'on_error $LINENO' ERR

LATEST="$(ls -t "$BACKUP_DIR"/vps-backup-*.tar.gz | head -n1)"

if [[ -z "${LATEST:-}" ]]; then
  log_err "no backup archive found in $BACKUP_DIR"
  exit 1
fi

if [[ ! -f "${LATEST}.sha256" ]]; then
  log_err "missing checksum file: ${LATEST}.sha256"
  exit 1
fi

log "latest backup: $LATEST"
log "ensuring target directory exists on ${TARGET_HOST}"
ssh "$TARGET_HOST" "mkdir -p '$TARGET_DIR'"

log "uploading archive and checksum to ${TARGET_HOST}:${TARGET_DIR}"
rsync -avz "$LATEST" "${LATEST}.sha256" "${TARGET_HOST}:${TARGET_DIR}/"

log "cleaning old backups on ${TARGET_HOST}"
ssh "$TARGET_HOST" "
  ls -t ${TARGET_DIR}/vps-backup-*.tar.gz 2>/dev/null | tail -n +8 | xargs -r rm -f
  ls -t ${TARGET_DIR}/vps-backup-*.tar.gz.sha256 2>/dev/null | tail -n +8 | xargs -r rm -f
"

log "offsite copy completed"
