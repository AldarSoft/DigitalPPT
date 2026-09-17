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

## PostgreSQL Release Test

The test runner creates an isolated `test_digital_ptt` database and never uses
the production database for test records. Grant database creation only for the
duration of the test, then revoke it even when a test fails:

```bash
sudo -u postgres psql -c "ALTER ROLE digital_ptt CREATEDB;"
cd /srv/digitalptt/backend
../.venv/bin/python manage.py test users products core licensing payments orders quotes api \
  --settings=config.settings.test
sudo -u postgres psql -c "ALTER ROLE digital_ptt NOCREATEDB;"
sudo -u postgres psql -tAc \
  "SELECT rolcreatedb FROM pg_roles WHERE rolname='digital_ptt';"
```

The final query must print `f`. If the test process is interrupted, revoke the
privilege manually before continuing.

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

## Product Presentation Release

Deploy the backend and frontend together for this release. Run the PostgreSQL
backup script first, then apply migrations and rebuild the frontend using the
normal deployment procedure. The new migrations are additive:

- `core.0020` adds shared product page defaults.
- `products.0009` adds presentation overrides and explicit highlight selection.
- `products.0010` assigns existing product templates and preserves the first four
  radio specifications as highlights. Existing specification values are retained.

For the temporary IP test installation, restart `digitalptt-ip-test-web` and
`digitalptt-ip-test-worker` after deploying; validated production installations
use `digitalptt-web` and `digitalptt-worker` instead.

In Site settings, review Product page defaults before publishing. In Products,
each product inherits the selected template and information badges. Customize
copies one section into the product's overrides; Reset to defaults removes that
section's override. Global edits affect inherited sections only. Visibility and
ordering are editable, and online payment badges appear only when a live online
provider is available. Editing descriptive content never enables payments.

Public catalog requests return only published, active products in active
categories, including when the visitor is an administrator. Inventory screens
request `?workspace=admin`; the `/catalog/<slug>/preview/` endpoint requires
inventory permission. The admin product editor links to the saved preview.

After deployment, verify a draft is absent from the shop, homepage and direct
product URL, then verify its authorized preview and a published product's badges.

## Per-Radio Licensing Release

This release keeps existing capacity licenses unchanged. The schema migration
does not convert the live license product automatically. Activate per-radio
billing only after the application migration succeeds and the command confirms
that no draft or pending legacy order references the plan.

Before the release, create and verify a database backup. During a short
maintenance window, stop the web and notification worker, deploy the backend and
frontend together, and run migrations. Then activate the selected annual plan:

```bash
cd /srv/digitalptt
.venv/bin/python backend/manage.py configure_per_radio_license \
  --sku LIC-RA-BUS-200 \
  --unit-price 120.00 \
  --term-days 365 \
  --settings=config.settings.prod
```

Do not bypass the command if it reports draft or pending orders. Cancel and
recreate those unpaid orders under the new pricing, or complete them under the
legacy model before retrying. If issued legacy licenses exist, preserve their
plan and renewal price: create a separate per-radio license product and assign
the radio products to it. The command clears sale and bulk pricing so every
radio receives the same annual `$120` charge.

Published per-radio plans appear in the shop with **Request coverage quote**.
Signed-in customers can select uncovered radios from their organization; the
request stores those paid order lines as immutable coverage targets. Staff use
the normal quote and invoice workflow. No license is created when the quote is
submitted or invoiced. Confirming the invoice payment creates one grouped
365-day license and allocates it only to the selected radios. If eligibility
changed while the quote was pending, payment confirmation stops for staff
review instead of silently reallocating coverage.

Restart the production web and worker services after activation. Temporary IP
installations use `digitalptt-ip-test-web` and `digitalptt-ip-test-worker`.
Confirm `/health/`, then verify these cases in the UI:

- One radio adds one annual plan unit for `$120`.
- Five radios add one plan line with quantity five and a `$600` line total.
- A successful payment creates one grouped license covering five radios.
- A later order creates a separate group with its own expiry date.
- Renewing a five-radio group charges five annual units and extends it once.
- Existing capacity licenses still display and renew as legacy licenses.

If a paid radio order remains uncovered after a plan migration or provisioning
failure, open the organization in **Admin > License management** and use **Add
corrective coverage**. Select only the affected paid order lines, confirm the
start date, and enter a specific audit reason. The action creates one grouped
per-radio license, replaces stale incompatible allocations, and records the
administrator and allocation changes in license history. It deliberately does
not create an order, invoice, or payment and must not be used to grant coverage
for unpaid radios.
