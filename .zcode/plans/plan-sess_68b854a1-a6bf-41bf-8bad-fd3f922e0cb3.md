# Phase 6: Privacy and Authorization

Decisions confirmed with user: License Managers keep licenses/capacity/renewal/team access but lose organization orders, addresses, and billing (Owner + staff only). Add a safe owner-only organization deletion endpoint (orgs with any history cannot be deleted).

## 1. Owner / License Manager matrix (backend authoritative)

- `licensing/permissions.py` `OrganizationAccessPolicy`:
  - `can_view` (licenses, team read, org info) — any active member or licensed staff. Unchanged.
  - `can_manage_licenses` — unchanged (member-level; real mutations already guarded in services: adjust=staff, cancel=owner+password, renew=member).
  - `can_manage_billing` — keep as-is (members) because it gates **license renewal payments**, which stay available to License Managers (their core role).
  - New `can_pay_orders(user, organization)` — staff with `confirm_bank_payments` or **Owner only**.
  - New `can_view_orders(user, organization)` — staff with `manage_orders` or **Owner only**.
- `payments/services.py` `can_pay_order` → uses `can_pay_orders` for organization-linked orders (order owner can still pay their own order; renewal attempts keep using `can_manage_billing`).
- `orders/views.py` `get_queryset`: with an `organization` filter, only owners/staff get the org's orders; License Managers get only their own orders (the `user=self.request.user` scope) so no addresses/billing/PII of org orders ever reaches them. `OrderSerializer` stays as-is (PII only travels to authorized viewers).
- Billing-email masking for License Managers: `OrganizationSummaryService.for_user` and `OrganizationSettingsView.get` return `billing_email=""` for non-owner members; frontend shows an empty state.
- Tests: manager cannot list org orders, cannot pay an org order, still can renew a license; owner/staff unaffected.

## 2. Safe owner-only organization deletion

- `licensing/services.py` `OrganizationService.delete_organization(*, organization, actor)`: atomic; requires owner role (+`can_manage_team`); refuses with specific `ValidationError`s when the org has any licenses, orders, license events, other active members, or pending invitations (immutable history makes real orgs undeletable by design); otherwise deletes the org (memberships cascade).
- New `DELETE /api/v1/licensing/organizations/<pk>/` view (`OrganizationDeleteView`, IsAuthenticated + service guards). Frontend: `api.deleteOrganization(organizationId)` and an owner-only "Delete organization" danger section in `OrganizationSettingsPanel` with inline confirmation (matching licensing UI patterns).
- Tests: owner deletes empty org; blocked by license/order/event/member/invitation; manager forbidden.

## 3. Simplified public inventory availability

- `products/serializers.py` split:
  - `ProductSerializer` becomes the **public** shape: drops `on_hand_inventory_quantity`, `reserved_inventory_quantity`, `backordered_inventory_quantity`, `status`, `is_active`, `created_at`, `updated_at`. Keeps `inventory_quantity` as the sellable availability signal (on-hand minus reservations), plus all catalog/licensing fields.
  - `AdminProductSerializer` adds back the exact quantities (`on_hand`, `reserved`, `backordered`), `status`, `is_active`, timestamps, and `cost_price`. `ProductViewSet.get_serializer_class` already routes staff with `manage_inventory` to it; everyone else (including anonymous) gets the public shape.
- Frontend `types.ts`: admin-only product fields become optional; admin pages unaffected (staff always receive them). Update the one order test that asserted anonymous catalog exposure of reserved/on-hand counts, and add a products test asserting the public shape omits exact quantities while the admin shape includes them.

## 4. URL-scheme validation for administrator-configured links

- `common/validators.py`: `validate_store_url` (accepts `""`, relative `/...` and `#...`, `https://`, `mailto:`, `tel:`; rejects `javascript:`, `data:`, other schemes) plus JSON-list variant for resource entries.
- `core/models.py`: `Banner.clean()` validates `cta_url` (and `image_url`); `SiteSetting.clean()` validates `homepage_hero_secondary_cta_url`, `homepage_contact_cta_url`, and the `url` keys in `homepage_resources` JSON. Admin serializers surface these errors.
- Frontend `HomePage.tsx` `StoreLink`: defensive render — only allowed schemes/relative paths become `href`; anything else falls back to `#`.
- Tests: `javascript:`/`data:` rejected for Banner and SiteSetting; https, relative, mailto accepted.

## 5. Protect API documentation in production

- `config/settings/base.py`: `API_DOCS_ENABLED = env("API_DOCS_ENABLED", default=DEBUG, cast=bool)`; `config/settings/prod.py`: explicit `env("API_DOCS_ENABLED", default=False, cast=bool)`. `SPECTACULAR_SETTINGS` gains `SWAGGER_UI_SETTINGS: {"persistAuthorization": False}`.
- `config/urls.py`: mount `api/schema/`, `api/docs/`, `api/redoc/` only when `API_DOCS_ENABLED` (schema generation via `manage.py spectacular` is unaffected — CI keeps working).
- `check_production_settings`: fail when production runs with `API_DOCS_ENABLED=True`.
- Tests: docs URLs return 404 under `override_settings(API_DOCS_ENABLED=False)`; the production-settings check fails when enabled.

## 6. Invoice privacy (verify + test)

Storage is already private (`PRIVATE_MEDIA_ROOT`, `private_media_storage`) with an authenticated, object-scoped `invoice-pdf` endpoint (queryset-scoped per quote owner). Add the missing proof:
- Tests: anonymous → 401; a different user → 404; quote owner → 200 with `private, no-store` and `nosniff` headers; staff with `manage_quotes` → 200.
- Keep the existing startup check that public and private media roots differ.

## 7. Documentation

Per the docsai policy, update `docsai/PROJECT_CONTEXT.md` (role matrix, public product field policy, API docs setting, org deletion rule) and check off the matching items in `docsai/SYSTEM_AUDIT_REMEDIATION_PLAN.md` (audit findings SEC-2026-09-06/11/12/13 portions).

## Verification

- Full backend suite (all apps — several existing tests touched: order org-scoping, products serializer exposure); `makemigrations --check`.
- Frontend: typecheck, eslint on changed files, unit tests, production build.

## Out of scope

Production storage backends/CORS/HSTS hardening (Phase 7, audit SEC-2026-09-07/08/09 remainder), instant payments, browser E2E tests (Phase 8).
