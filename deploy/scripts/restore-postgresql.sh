#!/usr/bin/env bash
set -Eeuo pipefail

APP_ROOT="${APP_ROOT:-/srv/digitalptt}"
PYTHON="${PYTHON:-$APP_ROOT/.venv/bin/python}"

if [[ "${1:-}" != "--yes" || -z "${2:-}" ]]; then
    printf 'Usage: %s --yes /absolute/path/to/backup.dump\n' "$0" >&2
    printf 'Stop the web and worker services before restoring.\n' >&2
    exit 1
fi

backup_path="$(realpath "$2")"
if [[ ! -f "$backup_path" ]]; then
    printf 'Backup does not exist: %s\n' "$backup_path" >&2
    exit 1
fi

pg_restore --list "$backup_path" >/dev/null
mapfile -d '' DB_CONFIG < <(
    cd "$APP_ROOT/backend"
    "$PYTHON" - <<'PY'
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

printf 'Restoring %s into database %s.\n' "$backup_path" "${DB_CONFIG[4]}"
PGPASSWORD="${DB_CONFIG[3]}" pg_restore \
    --host="${DB_CONFIG[0]}" \
    --port="${DB_CONFIG[1]}" \
    --username="${DB_CONFIG[2]}" \
    --dbname="${DB_CONFIG[4]}" \
    --clean \
    --if-exists \
    --no-owner \
    --no-privileges \
    "$backup_path"

printf 'Restore completed. Run migrations before starting services.\n'
