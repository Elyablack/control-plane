#!/usr/bin/env bash
set -Eeuo pipefail

BACKUP_DIR="/srv/backups"
STATE_DIR="/srv/control-plane/.state"
LOG_DIR="/srv/control-plane/logs"
STAMP_FILE="$STATE_DIR/last_backup_date"
LOCK_FILE="$STATE_DIR/run_backup.lock"
METRIC_FILE="/var/lib/node_exporter/textfile_collector/backup.prom"
LOG_FILE="$LOG_DIR/backup.log"
ERR_FILE="$LOG_DIR/backup.err.log"

mkdir -p "$STATE_DIR" "$LOG_DIR"

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "Backup job is already running."
  exit 1
fi

CURRENT_STEP="startup"

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

TODAY="$(date +%F)"

CURRENT_STEP="precheck"
if [[ -f "$STAMP_FILE" ]] && [[ "$(cat "$STAMP_FILE")" == "$TODAY" ]]; then
  log "backup already completed today (${TODAY}), skipping"
  exit 0
fi

log "=== backup start ==="

CURRENT_STEP="ansible_backup"
log "running ansible backup playbook"
ansible-playbook -i /srv/control-plane/inventory/hosts /srv/control-plane/backup/backup_vps.yml \
  >>"$LOG_FILE" 2>>"$ERR_FILE"

CURRENT_STEP="select_latest"
LATEST="$(ls -t /srv/backups/vps-backup-*.tar.gz | head -n1)"
if [[ -z "${LATEST:-}" ]]; then
  log_err "no backup archive found after playbook run"
  exit 1
fi
log "latest backup selected: $LATEST"

CURRENT_STEP="sha256"
log "generating sha256"
sha256sum "$LATEST" > "${LATEST}.sha256"

CURRENT_STEP="offsite_copy"
log "starting offsite copy"
BACKUP_LOG_FILE="$LOG_FILE" BACKUP_ERR_FILE="$ERR_FILE" \
  /srv/control-plane/backup/offsite_copy.sh >>"$LOG_FILE" 2>>"$ERR_FILE"

CURRENT_STEP="metric_update"
log "updating backup metric"
TS="$(date +%s)"
sudo mkdir -p /var/lib/node_exporter/textfile_collector
{
  echo "backup_last_success_unixtime $TS"
  echo "backup_last_success 1"
} | sudo tee "$METRIC_FILE" >/dev/null

CURRENT_STEP="state_update"
echo "$TODAY" > "$STAMP_FILE"
log "stamp updated: $STAMP_FILE"

CURRENT_STEP="finish"
log "=== backup end ==="
