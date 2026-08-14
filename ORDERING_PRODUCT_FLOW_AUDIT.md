# Ordering and Product Flow Audit

Date: 2026-08-14  
Scope: customer cart/checkout/payment, quote ordering, admin order handling, pricing, inventory, permissions, and visible statuses

## Result

Overall status: **Partially passed - payment and quote status fixes are required before production use.**

The core ordering flow is functional and the automated backend tests pass. Server-side pricing, bulk pricing, inventory validation, account ownership, status transitions, and paid-order cancellation protection are working. However, the audit found payment reconciliation and quote completion problems in the current live data.

## Test Coverage

| Area | Method | Result |
| --- | --- | --- |
| Customer direct checkout | API integration tests and code audit | Passed |
| Customer quote-to-order flow | API integration tests and live-data audit | Passed with status issue |
| Customer payment ownership | API integration tests | Passed |
| Admin order management | API integration tests and code audit | Passed with simulator issue |
| Bulk pricing | API integration tests and code audit | Passed |
| Inventory validation/deduction | API integration tests | Passed |
| Paid-order cancellation protection | API integration tests | Passed |
| Unpaid cancelled record hiding | Code and live-data audit | Partial |
| Payment reconciliation | Live-data and service audit | Failed |
| Frontend lint and typecheck | ESLint and TypeScript | Passed |
| Frontend production build | Vite build to temporary output | Passed with chunk-size warning |
| Django tests | 48 API/payment tests | Passed |
| Django system/migration checks | `check` and dry-run migration check | Passed |
| Fresh browser UI journey | In-app browser/Chrome attempt | Not completed: local browser connection unavailable |

## Customer Example 1: Instant Payment

Observed order: `ORD-2026-000020`

1. The customer selected one `IPTT710 Android`.
2. The server used the catalog unit price of `$430.00`.
3. A direct order was created with source `direct` and visible type `Instant payment`.
4. Payment `PAY-2026-000008` succeeded through the test bank-transfer provider.
5. Successful direct payment moved the order into processing and deducted stock.
6. The admin later completed the order.

Current status:

- Order: `Completed`
- Payment: `Completed` (`succeeded` internally)
- Total: `$430.00`
- Shipping: `$0.00`
- Stock deducted: yes
- Connected quote: none

## Customer Example 2: Quote-Based Order

Observed quote/order: `QTE-2026-000024` -> `ORD-2026-000021`

1. The customer requested a quote for four `IPTT810 / IPTT820` units.
2. The admin set the unit price to `$45.00` and shipping to `$670.00`.
3. The invoice created a quote-based pending order for `$850.00`.
4. The customer paid using test bank transfer: `PAY-2026-000009`.
5. Payment changed the internal order state to `scheduled`, displayed as `Processing`.
6. Admin processing deducted four units from stock.

Current status:

- Quote: `Completed` (`approved` internally)
- Order: `Processing`
- Payment: `Completed`
- Subtotal: `$180.00`
- Shipping: `$670.00`
- Total: `$850.00`
- Stock deducted: yes
- Order and quote are linked correctly

## Customer Example 3: Invoice Awaiting Payment

Observed quote/order: `QTE-2026-000022` -> `ORD-2026-000019`

1. The customer requested 21 `Universal Shoulder Holster` units.
2. The admin priced them at `$20.00` each and added `$50.00` shipping.
3. The system created a quote-based order for `$470.00`.
4. The customer has not paid and no payment attempt exists.

Current status:

- Quote: `Processing` (`quoted` internally)
- Order: `Pending`
- Payment: none
- Total: `$470.00`
- Stock deducted: no

## Status Flow

### Direct order

`Pending -> Processing -> Completed`

- Order creation: `Pending`
- Successful payment: `Processing`
- Admin fulfillment: `Completed`
- Unpaid orders may be cancelled; paid orders cannot be cancelled.

### Quote-based order

`Pending invoice -> Processing after payment -> Completed fulfillment`

- Invoice creates the order as `Pending`.
- Successful payment sets internal order status to `scheduled`, displayed as `Processing`.
- Admin moves fulfillment forward and stock is deducted.
- Admin completes the order.

### Visible status mapping

| Domain | Internal status | Visible status |
| --- | --- | --- |
| Order | `pending` | Pending |
| Order | `scheduled`, `processing` | Processing |
| Order | `completed` | Completed |
| Order | `cancelled` | Cancelled |
| Quote | `new` | Pending |
| Quote | `reviewing`, `quoted` | Processing |
| Quote | `approved` | Completed |
| Quote | `closed` | Cancelled |
| Payment | `pending` | Processing |
| Payment | `succeeded` | Completed |
| Payment | `failed`, `cancelled`, `expired`, `refunded` | Cancelled |

## Findings

### Critical: Multiple successful payments can exist for one order

Live order `ORD-2026-000018` has two successful `$4,550.00` payment attempts: `PAY-2026-000006` and `PAY-2026-000007`.

The checkout service allows multiple pending sessions with different idempotency keys. After one succeeds, another previously-created session can also succeed because confirming an already-processing order returns without blocking the second payment.

Required fix:

- Permit only one active payment session per order, or expire previous sessions when a new one starts.
- Lock the order and re-check for an existing successful payment during confirmation.
- Add a database/service-level guarantee and a regression test for duplicate success.

### High: Completed quote orders become `closed` and look cancelled

When a quote-based order becomes completed, the order model changes its quote to internal status `closed`. The frontend maps every `closed` quote to `Cancelled`, and the default quote query hides closed quotes.

Live examples:

- `QTE-2026-000021` -> completed order `ORD-2026-000018`
- `QTE-2026-000018` -> completed order `ORD-2026-000016`

This means completed quote history can disappear or appear cancelled.

Required fix:

- Separate quote `completed` and `cancelled` states, or derive the visible quote result from its linked paid/completed order.
- Keep completed quotes visible in customer and admin history.

### High: Admin payment simulation does not update the order

The admin Payments page can create a `succeeded` payment attempt without changing the order status or deducting stock. This behavior is explicitly asserted by the current test `test_admin_can_simulate_payment_without_changing_order`.

Required fix:

- Route successful admin simulations through the same payment-confirmation service as customer checkout, or label them as detached test records that are not real order payments.
- Do not let a detached simulation make `is_paid` true for cancellation and list logic.

### Medium: Stale pending payments remain on completed/cancelled orders

Live examples:

- `PAY-2026-000005` is pending while `ORD-2026-000001` is completed.
- `PAY-2026-000002` is pending while `ORD-2026-000011` is cancelled.

Required fix:

- Expire/cancel all remaining pending attempts when an order is paid, completed, or cancelled.
- Reject confirmation when the order is no longer payable.

### Medium: The Cancelled filters reveal unpaid cancelled history

Default order/quote lists hide unpaid cancelled records, but explicitly selecting the `Cancelled` filter bypasses that exclusion. The live database currently contains eight unpaid cancelled orders.

For quotes, `closed` also mixes true cancellations with completed quote orders, so the Cancelled filter cannot be trusted.

Required fix:

- Apply the unpaid-cancelled exclusion even when filtering.
- Resolve the quote `closed` status ambiguity first.

### Test Gap: No automated frontend ordering journey

There are strong API tests, but no automated browser test covering cart -> checkout -> payment -> account -> admin order processing. A fresh browser run could not be completed during this audit because the in-app browser could not reach the recovered local frontend and Chrome was unavailable.

Recommended browser tests:

1. Customer direct purchase with normal price.
2. Customer direct purchase crossing the bulk-price threshold.
3. Customer quote submission, admin invoice, customer payment, and admin completion.
4. Duplicate-click/payment-session protection.
5. Client/admin visibility of Pending, Processing, Completed, and Cancelled.
6. Linked `ORD-...` and `QTE-...` navigation from both account types.

## Confirmed Working Rules

- Customers must sign in before direct checkout.
- Customers cannot create admin orders.
- Customers can only pay their own orders.
- Product price is calculated on the server, not trusted from the browser.
- Bulk price is applied at the configured quantity threshold.
- Hidden/unpublished products cannot be ordered or quoted.
- Checkout rejects quantities above available stock.
- Checkout idempotency prevents duplicate orders for the same checkout key.
- Stock is deducted when fulfillment enters processing/completed.
- Cancelling an unpaid processed order restores deducted stock.
- Completed orders are terminal.
- Orders with successful payments cannot be cancelled.
- Quote invoices can be sent without negotiation messages.
- Quote and order IDs are linked and exposed to both admin and customer views.

## Recommended Fix Order

1. Block duplicate successful payments and invalidate other active sessions.
2. Separate completed quotes from cancelled quotes.
3. Make admin payment simulation use safe order/payment semantics.
4. Clean up stale pending payment attempts.
5. Make cancelled-list filtering follow the intended visibility rule.
6. Add one end-to-end browser test for direct orders and one for quote orders.

## Verification Commands

- Backend: 48 tests passed.
- Django system check: passed.
- Migration drift check: no changes detected.
- Frontend ESLint: passed.
- Frontend TypeScript check: passed.
- Frontend production build: passed when built to a clean temporary directory.
- Normal `frontend/dist` build remains blocked by an existing Windows lock on `dist/assets`; this is an environment/file-lock issue, not a compile failure.
