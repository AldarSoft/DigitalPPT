# Phase 1 Review Fixes

Status: complete  
Scope: Phase 1 storefront, account, admin quote/order, invoice, and status cleanup

## Summary

This file tracks the review changes collected after the Phase 1 review. One
small additional change is still undecided and should be added later when the
fix work starts.

## Task List

### 1. Remove top announcement banner - Complete

- Remove the top blue announcement strip from the public layout.
- Remove the visible text:
  - `GLOBAL RADIO SOLUTIONS`
  - `QUOTE SUPPORT`
  - `EXPERT SUPPORT`
- Confirm removing the banner does not leave extra top spacing above the main
  header.
- Check desktop and mobile header spacing after removal.

### 2. Clean up admin `/account` page - Complete

- When the logged-in user is staff/admin, simplify `/account`.
- Hide or remove admin access to customer-specific account sections:
  - Quote requests
  - Past orders
  - Address
- Keep only the profile/account settings that make sense for a staff user.
- Admin operational work should remain in `/admin`, not `/account`.
- Update any account page intro copy so it does not mention hidden sections for
  staff users.

### 3. Consolidate client account address forms - Complete

- Remove duplicated address forms from the client `/account` experience.
- Move the separate Address page/section into Account settings.
- Account settings should contain the main account/customer address.
- Add a checkbox for shipping behavior:
  - `Use a different shipping address`
- If unchecked, use the account/customer address as the shipping address.
- If checked, show a separate shipping address form.
- Ensure shipping address fields are clearly separate from the main account
  address fields.
- Preserve existing saved address data where possible.

### 4. Make negotiation message optional in admin invoice flow - Complete

- In the admin quote/invoice section, add an optional checkbox above the invoice
  fields.
- Default state: unchecked.
- When unchecked, admin can proceed with invoice calculation and invoice sending
  without adding a negotiation/additional message.
- When checked, show the additional message/request area so admin can ask for
  more information before sending an invoice.
- Make the UI copy clear that messaging is optional.

### 5. Auto-fill unit price and add simple shipment price - Complete

- Auto-fill unit price in the admin invoice/pricing section from product data.
- Add support for bulk pricing rules when quantity passes a configured range.
- Example:
  - normal unit price: `$25`
  - bulk unit price: `$22`
- Show the calculated unit price clearly before sending invoice.
- Add a simple shipment/shipping price input field.
- Ensure invoice total calculation includes:
  - quantity
  - unit price
  - bulk price if applicable
  - shipment price
- Keep calculation server-authoritative where backend pricing already exists.

### 6. Remove required two-sided message rule before invoice - Complete

- Remove the rule that requires both client and admin to send messages before
  admin can send an invoice.
- Admin should have two invoice flow choices:
  - calculate and send invoice immediately
  - request additional information first, then send invoice
- Invoice eligibility should not depend on negotiation message count.
- Update backend validation, frontend disabled states, and helper text to match
  the new rule.

### 7. Remove Promotions page from admin dashboard - Complete

- Remove Promotions from the admin sidebar/navigation.
- Remove or hide the Promotions route/page from the active admin dashboard.
- Ensure no broken links remain.
- Keep backend promotion code untouched unless it directly causes UI exposure or
  routing issues.

### 8. Hide unpaid cancelled quotes and orders from lists - Complete

- If a quote or order is cancelled before payment is sent, do not show it in
  normal quote/order lists.
- Apply this cleanup to both client and admin panels.
- Confirm whether staff still needs a hidden/archive filter later; do not build
  that unless explicitly requested.
- Avoid deleting historical records from the database. This is a listing/filter
  behavior change unless later review says otherwise.

### 9. Simplify status labels across panels - Complete

- Simplify visible status names in admin and client panels.
- Prefer simple customer-readable labels:
  - `Pending`
  - `Processing`
  - `Completed`
  - `Cancelled`
- Reduce confusing internal terms where they appear in user-facing tables,
  badges, logs, and summary cards.
- Keep internal backend enum values if changing them would create unnecessary
  migration/risk; map them to simpler display labels in serializers or frontend
  helpers where appropriate.

### 10. Rename quote converted status/log step to completed - Complete

- In quote processing logs/banners, change the 4th step/status wording from
  `Converted` to `Completed`.
- Reason: by that point the client has already paid, so `Completed` is clearer.
- Check both admin and client views for the old `Converted` wording.
- Update status badge display and timeline/log display if both use separate
  mapping logic.

## Notes For Implementation

- Keep changes scoped to Phase 1 behavior and UI cleanup.
- Do not start Phase 1.1 subscription/licensing work from this task file.
- Do not delete historical order/quote data unless explicitly requested.
- Prefer display mapping over database enum changes when possible.
- Run relevant frontend and backend checks after implementation.
