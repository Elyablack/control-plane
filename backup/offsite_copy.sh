#!/usr/bin/env bash
set -euo pipefail

BACKUP_DIR="/srv/backups"
TARGET_HOST="admin"
TARGET_DIR="/home/admin1/infra-backups"

LATEST="$(ls -t "$BACKUP_DIR"/vps-backup-*.tar.gz | head -n1)"

if [[ -z "${LATEST:-}" ]]; then
  echo "No backup archive found in $BACKUP_DIR" >&2
  exit 1
fi

if [[ ! -f "${LATEST}.sha256" ]]; then
  echo "Missing checksum file: ${LATEST}.sha256" >&2
  exit 1
fi

echo "Latest backup: $LATEST"
echo "Uploading to ${TARGET_HOST}..."

ssh "$TARGET_HOST" "mkdir -p '$TARGET_DIR'"
rsync -avz "$LATEST" "${LATEST}.sha256" "${TARGET_HOST}:${TARGET_DIR}/"

echo "Cleaning old backups on ${TARGET_HOST}..."
ssh "$TARGET_HOST" "
  ls -t ${TARGET_DIR}/vps-backup-*.tar.gz 2>/dev/null | tail -n +8 | xargs -r rm -f
  ls -t ${TARGET_DIR}/vps-backup-*.tar.gz.sha256 2>/dev/null | tail -n +8 | xargs -r rm -f
"

echo "Offsite copy completed."
