#!/usr/bin/env bash
set -euo pipefail

BACKUP_DIR="/srv/backups"
STATE_DIR="/srv/control-plane/.state"
STAMP_FILE="$STATE_DIR/last_backup_date"

mkdir -p "$STATE_DIR"

TODAY="$(date +%F)"

if [[ -f "$STAMP_FILE" ]] && [[ "$(cat "$STAMP_FILE")" == "$TODAY" ]]; then
  echo "Backup already done today ($TODAY), skipping."
  exit 0
fi

echo "=== backup start $(date -u '+%Y-%m-%d %H:%M:%S UTC') ==="

ansible-playbook -i /srv/control-plane/inventory/hosts /srv/control-plane/backup/backup_vps.yml

LATEST="$(ls -t /srv/backups/vps-backup-*.tar.gz | head -n1)"

echo "Generating SHA256..."
sha256sum "$LATEST" > "$LATEST.sha256"

echo "Running offsite copy..."
/srv/control-plane/backup/offsite_copy.sh

echo "Updating backup metric..."
TS="$(date +%s)"

sudo mkdir -p /var/lib/node_exporter/textfile_collector
{
  echo "backup_last_success_unixtime $TS"
  echo "backup_last_success 1"
} | sudo tee /var/lib/node_exporter/textfile_collector/backup.prom >/dev/null

echo "$TODAY" > "$STAMP_FILE"

echo "=== backup end $(date -u '+%Y-%m-%d %H:%M:%S UTC') ==="
