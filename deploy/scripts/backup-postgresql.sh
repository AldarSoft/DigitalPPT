#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

APP_ROOT="${APP_ROOT:-/srv/digitalptt}"
PYTHON="${PYTHON:-$APP_ROOT/.venv/bin/python}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/digitalptt/postgresql}"
BACKUP_RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"

mkdir -p "$BACKUP_DIR"
mapfile -d '' DB_CONFIG < <(
    cd "$APP_ROOT/backend"
    "$PYTHON" - <<'PY'
import os
import sys
from pathlib import Path

from common.env import env, load_env_file

load_env_file(Path(".env"))
values = (
    env("POSTGRES_HOST", "127.0.0.1"),
    env("POSTGRES_PORT", "5432"),
    env("POSTGRES_USER", "digital_ptt"),
    env("POSTGRES_PASSWORD", ""),
    env("POSTGRES_DB", "digital_ptt"),
)
for value in values:
    sys.stdout.write(f"{value}\0")
PY
)

if [[ "${#DB_CONFIG[@]}" -ne 5 ]]; then
    printf 'Could not load PostgreSQL configuration.\n' >&2
    exit 1
fi

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
destination="$BACKUP_DIR/digital_ptt_${timestamp}.dump"
temporary="$destination.partial"

PGPASSWORD="${DB_CONFIG[3]}" pg_dump \
    --host="${DB_CONFIG[0]}" \
    --port="${DB_CONFIG[1]}" \
    --username="${DB_CONFIG[2]}" \
    --dbname="${DB_CONFIG[4]}" \
    --format=custom \
    --no-owner \
    --file="$temporary"

mv "$temporary" "$destination"
find "$BACKUP_DIR" -maxdepth 1 -type f -name 'digital_ptt_*.dump' \
    -mtime "+$BACKUP_RETENTION_DAYS" -delete

printf 'Created %s\n' "$destination"
