#!/usr/bin/env bash
set -Eeuo pipefail

APP_ROOT="${APP_ROOT:-/srv/digitalptt}"
DEPLOY_BRANCH="${DEPLOY_BRANCH:-main}"
DEPLOY_SKIP_UPDATE="${DEPLOY_SKIP_UPDATE:-0}"
VENV="${VENV:-$APP_ROOT/.venv}"
PREVIOUS_REVISION=""

fail() {
    printf 'Deployment failed.\n' >&2
    if [[ -n "$PREVIOUS_REVISION" ]]; then
        printf 'Previous revision: %s\n' "$PREVIOUS_REVISION" >&2
        printf 'Review DEPLOYMENT.md before rolling back code or migrations.\n' >&2
    fi
}
trap fail ERR

if [[ "${EUID}" -eq 0 ]]; then
    printf 'Run this script as the deploy user, not root.\n' >&2
    exit 1
fi

cd "$APP_ROOT"

if [[ ! -f backend/.env ]]; then
    printf 'Missing %s/backend/.env\n' "$APP_ROOT" >&2
    exit 1
fi

if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
    printf 'Tracked files contain local changes; deployment stopped.\n' >&2
    exit 1
fi

PREVIOUS_REVISION="$(git rev-parse HEAD)"
printf '%s\n' "$PREVIOUS_REVISION" > .previous-deploy-revision
if [[ "$DEPLOY_SKIP_UPDATE" != "1" ]]; then
    git fetch --prune origin
    git checkout "$DEPLOY_BRANCH"
    git pull --ff-only origin "$DEPLOY_BRANCH"
fi

python3 -m venv "$VENV"
"$VENV/bin/python" -m pip install --disable-pip-version-check -r backend/requirements.txt

(
    cd frontend
    npm ci
    npm run build
)

mkdir -p backend/logs backend/media backend/staticfiles

(
    cd backend
    "$VENV/bin/python" manage.py check --deploy --settings=config.settings.prod
    "$VENV/bin/python" manage.py check_production_settings --settings=config.settings.prod
    "$VENV/bin/python" manage.py migrate --noinput --settings=config.settings.prod
    "$VENV/bin/python" manage.py collectstatic --noinput --settings=config.settings.prod
)

sudo systemctl daemon-reload
sudo systemctl restart digitalptt-web digitalptt-worker
sudo systemctl enable --now license-reconciliation.timer

printf 'Deployed revision %s\n' "$(git rev-parse HEAD)"
