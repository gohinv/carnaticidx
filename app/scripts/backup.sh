set -euo pipefail

APP_DIR="$HOME/carnaticidx"
ENV_FILE="$APP_DIR/.env.production"
BACKUP_DIR="/var/backups/carnaticidx"
REMOTE="dropbox:carnaticidx-backups"
RETENTION_DAYS=5
DATE="$(date +%F)"
STAMP="$(date +%F_%H%M%S)"
FILE="carnaticidx-${STAMP}.sql.gz"
LOG="/var/log/carnaticidx-backup.log"

mkdir -p "$BACKUP_DIR"

{
  echo "=== $(date -Is) backup start ==="
  cd "$APP_DIR"
  docker compose --env-file "$ENV_FILE" exec -T db \
    pg_dump -U gohitha -d carnaticidx | gzip > "${BACKUP_DIR}/${FILE}"
  rclone copy "${BACKUP_DIR}/${FILE}" "$REMOTE" --transfers 1
  # prune local backups older than RETENTION_DAYS
  find "$BACKUP_DIR" -name 'carnaticidx-*.sql.gz' -mtime +"${RETENTION_DAYS}" -delete
  # prune remote backups older than RETENTION_DAYS
  rclone delete "$REMOTE" --min-age "${RETENTION_DAYS}d"
  echo "=== $(date -Is) backup success: ${FILE} ==="
} >> "$LOG" 2>&1