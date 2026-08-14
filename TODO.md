# DigitalPPT TODO

## Objective
Capture the next implementation priorities for the current DigitalPPT project state and present a clear phase-based delivery plan.

## Executive summary
- Phase 1 (Rest): finish the remaining commerce checkout and order experience work, including payment flow stabilization and order tracking.
- Phase 1.1: build the subscription/license proof of concept for radio products with local lifecycle handling and invited-access support.
- Phase 1.2: reserve future work for the external RadioAdminPanel integration.

## Phase 1 (Current work plan) — 1 week
Goal: complete the commerce pricing, payment state, and order detail experience so checkout can operate reliably.

Key deliverables:
- Checkout idempotency and payment state modeling.
- Payment provider connection with direct checkout only after server-side pricing and validation.(not planned yet)
- Customer order detail pages, order timeline, and shipment tracking in the frontend.

What this means for the team:
- Focus on closing the remaining commerce flow gaps.
- Keep the checkout path server-driven and validated before moving to live payment.
- Deliver a usable order tracking experience for end customers. (could be useful)


## Phase 1.1 — 2-3 weeks
Goal: launch a local subscription/license management experience for radio products and prepare the system for later external admin sync.

Detailed implementation plan: `docsai/PHASE_1_1_SUBSCRIPTION_LICENSING_PLAN.md`

Planning note:
- A tight MVP may fit into 2 weeks if scope stays limited to local licensing, account tabs, invited access, and core lifecycle behavior.
- The safer estimate is 2-3 weeks because workbook import, permission testing, expiry behavior, and frontend QA can expand quickly.

Key deliverables:
- Domain model and database design for Subscription / License, RadioDevice, and AccountAccess.
- CustomerAccount/company ownership layer so subscriptions and licenses belong to the client organization, not only the original buyer.
- Role-based invited access so another approved user can manage the same subscription/license if the original buyer is unavailable.
- Product-to-license mapping, capacity tracking, and purchase-triggered license creation or extension.
- Customer account UI pages: Subscription Management, License page, and Invited Access.
- License lifecycle behavior: create new licenses, extend existing ones, calculate remaining days, and expire/deactivate radios.
- Team license support so one license can cover multiple radios within capacity.
- Local integration scaffolding for future RadioAdminPanel sync without requiring the external API today.

What this means for the team:
- Build the subscription/license capability as a local proof of concept.
- Keep external radio admin API work offboarded until later phases.
- Prioritize correctness of license lifecycle and user-facing management pages.

Phase 1.1 fixed task list:

Frontend:
- [ ] Build Subscription Management page.
- [ ] Build License Management page.
- [ ] Build Invited Access page.
- [ ] Build Company / Customer Account section.
- [ ] Build RadioAdmin placeholder account section.
- [ ] Add role-based UI states for owner, manager, and viewer.
- [ ] Add loading, empty, error, and permission-denied states.
- [ ] Make all pages responsive for desktop, tablet, and mobile.

Backend:
- [ ] Create `licensing` Django app.
- [ ] Design database for `CustomerAccount`.
- [ ] Design database for `AccountMembership`.
- [ ] Design database for `AccountInvitation`.
- [ ] Design database for `Subscription`.
- [ ] Design database for `License`.
- [ ] Design database for `RadioDevice`.
- [ ] Design database for `DeviceLicenseAssignment`.
- [ ] Design database for `LicenseEvent`.
- [ ] Design local placeholder for `RadioAdminAccount`.
- [ ] Add product-to-license mapping logic.
- [ ] Add license lifecycle logic: create, activate, extend, expire, deactivate.
- [ ] Add remaining-days calculation.
- [ ] Add license capacity tracking.
- [ ] Add team/company account permission logic.
- [ ] Add invited user permission logic.
- [ ] Add local-only subscription/license provisioning without external API sync.
- [ ] Add future API sync placeholder architecture.
- [ ] Add payment-success trigger for license creation or extension.
- [ ] Add expiry job/command to deactivate expired license radios.

API:
- [ ] Add `/api/v1/licensing/summary/`.
- [ ] Add `/api/v1/licensing/subscriptions/`.
- [ ] Add `/api/v1/licensing/licenses/`.
- [ ] Add `/api/v1/licensing/licenses/{number}/devices/`.
- [ ] Add `/api/v1/licensing/devices/`.
- [ ] Add `/api/v1/licensing/memberships/`.
- [ ] Add `/api/v1/licensing/invitations/`.
- [ ] Add `/api/v1/licensing/radio-admin-accounts/`.
- [ ] Add RadioAdmin reset/setup intent endpoint.

Core business rules:
- [ ] Subscription/license belongs to `CustomerAccount`, not only original buyer.
- [ ] Original buyer becomes first `owner`.
- [ ] Invited users can manage the same customer account by role.
- [ ] `owner` can manage billing, license, radios, users, and RadioAdmin controls.
- [ ] `manager` can manage licenses, radios, and invitations.
- [ ] `viewer` can only view.
- [ ] If original buyer is unavailable, invited owner/manager can continue renewal or license management.
- [ ] No external RadioAdminPanel API calls in this phase.
- [ ] No plaintext passwords or external API secrets stored.

Testing / QA:
- [ ] Test paid order provisions license exactly once.
- [ ] Test license extension calculation.
- [ ] Test expired license deactivates radios.
- [ ] Test capacity cannot be exceeded.
- [ ] Test invited user access permissions.
- [ ] Test users cannot access another company account.
- [ ] Test frontend responsive layouts.
- [ ] Run backend checks/tests.
- [ ] Run frontend lint/type/build.

Estimate:
- MVP: about 2 weeks.
- Safer full delivery: 2-3 weeks.

## Phase 1.2
- Not included yet.
- Future work: API connection and functional sync with RadioAdminPanel.


## Implementation notes
- Do not use `backend/api/` or `config/settings/legacy.py` for new work.
- Preserve the quote-first commerce model until payment is fully implemented.
- Keep frontend styling Tailwind-only and reuse shared recipes in `src/lib/tailwind-styles.ts`.
- Do not edit already-applied Django migrations; add new migrations when schema or stored-data changes are needed.


## Phase 1.1 details
### Domain model
- `Subscription` / `License`
  - `start_date`, `end_date`, `capacity`, `used_count`, `status` (`active`, `expired`, `pending`)
- `RadioDevice`
  - `model`, `type`, `serial_number`, `status` (`active`, `inactive`, `not sold`), `subscription_id`
- `AccountAccess`
  - owner account, invited users, permissions/access level


### Product/license mapping
- Use current radio product types as purchase triggers:
  - vehicle radios
  - in-person radios
  - in-person mini
  - in-person micro
  - wireless earphone
- First qualifying radio purchase should create a license.
- Subsequent device purchases should be added to the existing active license while:
  - the license duration has not expired
  - the license still has available capacity
- If the customer needs more devices than the current license capacity allows, they should be able to purchase an additional license.
- Licensed radios should be associated to the active license when activated.


### Account UI pages
- `Customer Account / Company`
  - subscriptions and licenses belong to the client company/group account, not only the original ordering user
  - original buyer becomes the first owner
  - invited users can continue managing the same account based on role permissions
- `Subscription Management`
  - show current license details, capacity used vs available, renewal/extend option
- `License Page`
  - show license start/end dates, remaining days, extension before expiration
- `Invited Access`
  - add/remove invited users, list users with access, manage shared account permissions


### License lifecycle behavior
- New purchase flow:
  - if no active license exists, create an annual license
  - if an active license exists, extend it and recalculate remaining days
- Extension calculation:
  - compute remaining days from current expiration
  - add new extension period on top of remaining days
- Expiration handling:
  - when a license expires, deactivate all associated radios
  - mark radios inactive in the local database
  - keep a record of expired license history


### Team licensing
- One license can cover multiple radios.
- Example: a 200-radio license can cover 70 now and 130 more later.
- Ensure purchases can be added under the same license until capacity is reached.


### Future radio admin integration planning
- Keep the external admin panel offboarded for now.
- Add local placeholder support for:
  - creating a `lvl4` admin account on purchase
  - marking that account as the “radio manager”
  - storing the intent to notify/sync when the external API exists
  - allowing the client to reset the `lvl4` admin password locally
- Later integration should:
  - create `lvl4` admin account automatically
  - send login details to the client
  - support `lvl3` management of `lvl4` admins


## Phase 1.1 milestones
- Phase 1.1 MVP
  - local subscription/license model
  - account pages for subscription, license, invited access
  - license extension logic
  - expiry deactivation of radios
- Phase 1.1 completion
  - team license capacity enforcement
  - product-radio matching by serial/SN
  - invited account UX and access controls
- Phase 1.2 external integration
  - radio admin site sync flow
  - `lvl4` admin account creation and notification
  - stronger validation around license/radio association


## Time planning

### Phase 1 (rest)
- Estimate: 1 week (5 workdays)

### Phase 1.1
- Estimate: 2-3 weeks (15 workdays)

### Phase 1.2
- Not included yet
- API connection and functional sync work with RadioAdminPanel
