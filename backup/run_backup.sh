#!/usr/bin/env bash
set -euo pipefail

BACKUP_DIR="/srv/backups"
STATE_DIR="/srv/control-plane/.state"
STAMP_FILE="$STATE_DIR/last_backup_date"
LOCK_FILE="$STATE_DIR/run_backup.lock"
METRIC_FILE="/var/lib/node_exporter/textfile_collector/backup.prom"

mkdir -p "$STATE_DIR"

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "Backup job is already running."
  exit 1
fi

log() {
  echo "[$(date -u '+%Y-%m-%d %H:%M:%S UTC')] $*"
}

TODAY="$(date +%F)"

if [[ -f "$STAMP_FILE" ]] && [[ "$(cat "$STAMP_FILE")" == "$TODAY" ]]; then
  log "Backup already completed today ($TODAY), skipping."
  exit 0
fi

log "=== backup start ==="

log "Running Ansible backup playbook..."
ansible-playbook -i /srv/control-plane/inventory/hosts /srv/control-plane/backup/backup_vps.yml

LATEST="$(ls -t /srv/backups/vps-backup-*.tar.gz | head -n1)"
if [[ -z "${LATEST:-}" ]]; then
  log "No backup archive found after playbook run."
  exit 1
fi

log "Generating SHA256 for $LATEST..."
sha256sum "$LATEST" > "${LATEST}.sha256"

log "Running offsite copy..."
/srv/control-plane/backup/offsite_copy.sh

log "Updating backup metric..."
TS="$(date +%s)"

sudo mkdir -p /var/lib/node_exporter/textfile_collector
{
  echo "backup_last_success_unixtime $TS"
  echo "backup_last_success 1"
} | sudo tee "$METRIC_FILE" >/dev/null

echo "$TODAY" > "$STAMP_FILE"

log "=== backup end ==="
