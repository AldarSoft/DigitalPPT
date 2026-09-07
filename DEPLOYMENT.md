# Digital PTT Droplet Deployment

This runbook targets Ubuntu 24.04 on a DigitalOcean Droplet. The production
layout uses Nginx, Gunicorn, PostgreSQL, a notification worker, and a systemd
timer for license reconciliation.

## Prerequisites

- A non-root `deploy` user with sudo and SSH-key access.
- A DNS name pointing to the Droplet before requesting TLS certificates.
- Python 3.12, Node.js 22, Nginx, PostgreSQL client/server, Git, and build tools.
- Microsoft Graph application credentials with permission to send as the site mailbox.
- An off-server destination for database and private-media backups.

Do not expose ports 5432, 8000, or 5173. Allow only SSH, HTTP, and HTTPS through
the DigitalOcean Cloud Firewall and UFW.

## Server Layout

```text
/srv/digitalptt                         repository checkout
/srv/digitalptt/.venv                   Python virtual environment
/srv/digitalptt/backend/.env            production secrets, mode 0600
/var/lib/digitalptt/private_media       protected invoice files
/var/backups/digitalptt/postgresql      temporary local database backups
```

Create the writable directories before starting services:

```bash
sudo install -d -o deploy -g www-data -m 0750 /srv/digitalptt
sudo install -d -o deploy -g www-data -m 0750 /var/lib/digitalptt/private_media
sudo install -d -o deploy -g deploy -m 0700 /var/backups/digitalptt/postgresql
```

## Checkout And Configuration

Clone the repository as `deploy`:

```bash
git clone https://github.com/AldarSoft/DigitalPPT.git /srv/digitalptt
cd /srv/digitalptt
cp backend/.env.production.example backend/.env
chmod 600 backend/.env
```

Replace every placeholder in `backend/.env`. Generate `DJANGO_SECRET_KEY` and
`JWT_SIGNING_KEY` independently with `openssl rand -base64 64`. Production
validation remains blocked until PostgreSQL, HTTPS origins, and a real email
delivery path are configured.

## PostgreSQL

For a local database, create the role and database without exposing PostgreSQL:

```bash
sudo -u postgres createuser --pwprompt digital_ptt
sudo -u postgres createdb --owner=digital_ptt digital_ptt
psql -h 127.0.0.1 -U digital_ptt -d digital_ptt -c "SELECT 1;"
```

Put the same generated role password in `backend/.env`.

## Install Services

Replace `example.com` in the Nginx template, then install the service files:

```bash
sudo cp deploy/systemd/*.service deploy/systemd/*.timer /etc/systemd/system/
sudo cp deploy/nginx/digitalptt.conf /etc/nginx/sites-available/digitalptt
sudo ln -s /etc/nginx/sites-available/digitalptt /etc/nginx/sites-enabled/digitalptt
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx
sudo systemctl daemon-reload
sudo systemctl enable digitalptt-web digitalptt-worker
sudo systemctl enable license-reconciliation.timer operations-check.timer
```

The service user must be able to write application logs and public uploads:

```bash
sudo install -d -o deploy -g www-data -m 0750 backend/logs backend/media backend/staticfiles
```

## Deploy

Install Node.js 22 before the first deployment. Then:

```bash
chmod +x deploy/scripts/*.sh
./deploy/scripts/deploy.sh
```

The script refuses root execution and dirty tracked files. It fetches `main`,
installs dependencies, builds React, validates production settings, applies
migrations, collects static assets, restarts services, and enables the timer.

Inspect status after every deployment:

```bash
sudo systemctl status digitalptt-web digitalptt-worker --no-pager
sudo systemctl list-timers license-reconciliation.timer operations-check.timer
sudo journalctl -u digitalptt-web -u digitalptt-worker --since "10 minutes ago"
curl --fail http://127.0.0.1:8000/health/
```

## Domain And HTTPS

After the domain resolves to the Droplet, install Certbot and request TLS:

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d example.com -d www.example.com
sudo certbot renew --dry-run
```

Confirm that Certbot changed the HTTP server to redirect to HTTPS. Add the
following header inside the generated HTTPS server block after HTTPS works:

```nginx
add_header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload" always;
```

Run the deployed smoke test from the backend virtual environment:

```bash
cd /srv/digitalptt/backend
../.venv/bin/python scripts/deployment_smoke_test.py https://example.com
```

## Backups And Restore Test

Create a database backup:

```bash
sudo -u deploy /srv/digitalptt/deploy/scripts/backup-postgresql.sh
```

Copy each completed dump and `/var/lib/digitalptt/private_media` to storage
outside this Droplet. A local backup alone does not protect against Droplet loss.

The payment reconciliation units are installed but do not need to be enabled
while customer-facing payment providers are disabled. Enable the timer when a
live provider and its reconciliation adapter are configured:

```bash
sudo systemctl enable --now payment-reconciliation.timer
```

Test restoration into an isolated database before launch and after material
schema changes. Never test a restore against the live production database.

For an approved production restore, stop services first:

```bash
sudo systemctl stop digitalptt-web digitalptt-worker
sudo -u deploy /srv/digitalptt/deploy/scripts/restore-postgresql.sh --yes /absolute/backup.dump
cd /srv/digitalptt/backend
../.venv/bin/python manage.py migrate --settings=config.settings.prod
sudo systemctl start digitalptt-web digitalptt-worker
```

## Rollback

`deploy.sh` records the previous Git revision in `.previous-deploy-revision`.
Before rolling back, inspect migrations made by the failed release. Database
migrations are not automatically reversed because reverse operations can destroy
data.

When the previous code is compatible with the current schema:

```bash
cd /srv/digitalptt
git checkout "$(cat .previous-deploy-revision)"
DEPLOY_SKIP_UPDATE=1 ./deploy/scripts/deploy.sh
```

For destructive or incompatible migrations, restore the verified database dump
and the matching code revision during a maintenance window.
