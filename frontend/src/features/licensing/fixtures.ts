import type {
  AdminOrganizationLicenseDetail,
  AdminOrganizationLicenseListResponse,
  ClientLicenseDetail,
  ClientLicenseListResponse,
  OrganizationTeamResponse,
} from './types'

export const clientLicenseListFixture: ClientLicenseListResponse = {
  organization: { id: 1, public_id: 'a9f43d38-244e-4f18-98a3-0ab39b4cb55d', name: 'Digital PTT Aldarsoft', role: 'owner' },
  summary: { license_count: 2, active_license_count: 2, expiring_soon_count: 0, expired_license_count: 0, total_capacity: 400, used_capacity: 250, available_capacity: 150, next_expiry: '2027-08-17', next_expiry_remaining_days: 363, licensed_product_count: 4, licensed_product_quantity: 250, usable_license_capacity: 400, overflow_quantity: 0 },
  renewal_request: { issued: false, issued_at: null },
  licenses: [
    { id: 1, license_number: 'LIC-RA-01482', name: 'RadioAdmin License 01', plan_name: 'RadioAdmin Business', plan_sku: 'LIC-RA-BUS-200', status: 'active', capacity: 200, used_capacity: 200, available_capacity: 0, capacity_percentage: 100, starts_on: '2026-08-18', expires_on: '2027-08-17', renews_on: '2027-08-18', remaining_days: 363, has_pending_renewal: false },
    { id: 2, license_number: 'LIC-RA-01509', name: 'RadioAdmin License 02', plan_name: 'RadioAdmin Business', plan_sku: 'LIC-RA-BUS-200', status: 'active', capacity: 200, used_capacity: 50, available_capacity: 150, capacity_percentage: 25, starts_on: '2027-03-04', expires_on: '2028-03-03', renews_on: '2028-03-04', remaining_days: 562, has_pending_renewal: true },
  ],
}

export const clientLicenseDetailFixture: ClientLicenseDetail = {
  license_number: 'LIC-RA-01482',
  name: 'RadioAdmin License 01',
  plan_name: 'RadioAdmin Business',
  plan_sku: 'LIC-RA-BUS-200',
  status: 'active',
  capacity: 200,
  used_capacity: 200,
  available_capacity: 0,
  starts_on: '2026-08-18',
  expires_on: '2027-08-17',
  renews_on: '2027-08-18',
  remaining_days: 363,
  has_pending_renewal: false,
  subscription: { term_days: 365, starts_on: '2026-08-18', expires_on: '2027-08-17', renews_on: '2027-08-18', remaining_days: 363, source_order: { order_number: 'ORD-2026-000021', ordered_at: '2026-08-18T09:30:00Z' } },
  allocations: [
    { id: 1, product: { id: 1, name: 'IPTT710 Android', sku: 'IPTT710' }, quantity: 120, source_order: { order_number: 'ORD-2026-000021', ordered_at: '2026-01-12T09:30:00Z' } },
    { id: 2, product: { id: 2, name: 'IPTT810 / IPTT820', sku: 'IPTT810' }, quantity: 60, source_order: { order_number: 'ORD-2026-000020', ordered_at: '2026-06-14T09:30:00Z' } },
    { id: 3, product: { id: 3, name: 'Dispatcher Console', sku: 'DISP-001' }, quantity: 20, source_order: { order_number: 'ORD-2026-000020', ordered_at: '2026-06-14T09:30:00Z' } },
  ],
}

export const organizationTeamFixture: OrganizationTeamResponse = {
  organization: { id: 1, name: 'Digital PTT Aldarsoft' },
  current_user_role: 'owner',
  owner: { id: 1, name: 'Client Local', email: 'client@digitalptt.local' },
  license_managers: [
    { membership_id: 2, name: 'B. Magnai', email: 'bayar@aldarsoft.mn', role: 'license_manager', status: 'active' },
    { membership_id: 3, name: 'T. Sukh', email: 'support@aldarsoft.mn', role: 'license_manager', status: 'active' },
  ],
  pending_invitations: [{ invitation_id: 1, email: 'odavaa@aldarsoft.mn', role: 'license_manager', status: 'pending', expires_at: '2026-08-26T09:30:00Z' }],
  permissions: { can_invite: true, can_revoke_manager: true, can_transfer_ownership: true },
}

export const adminOrganizationListFixture: AdminOrganizationLicenseListResponse = {
  summary: { organizations_with_licenses: 42, active_licenses: 1268, licenses_expiring_in_60_days: 86, organizations_needing_capacity: 7, payments_in_review: 4 },
  count: 4,
  next: null,
  previous: null,
  results: [
    { id: 1, name: 'Digital PTT Aldarsoft', owner: { name: 'Client Local', email: 'client@digitalptt.local' }, license_count: 2, used_capacity: 250, total_capacity: 400, licensed_product_quantity: 250, usable_license_capacity: 400, overflow_quantity: 0, next_expiry: '2027-08-17', status: 'expiring_soon' },
    { id: 2, name: 'Global Radio Solutions', owner: { name: 'S. Bat', email: 'sales@globalradio.com' }, license_count: 4, used_capacity: 430, total_capacity: 800, licensed_product_quantity: 430, usable_license_capacity: 800, overflow_quantity: 0, next_expiry: '2027-12-03', status: 'active' },
    { id: 3, name: 'Nomad Logistics', owner: { name: 'A. Enkh', email: 'admin@nomadlogistics.mn' }, license_count: 1, used_capacity: 50, total_capacity: 200, licensed_product_quantity: 250, usable_license_capacity: 200, overflow_quantity: 50, next_expiry: '2027-07-01', status: 'pending_payment' },
    { id: 4, name: 'Mongolian Mining Corp', owner: { name: 'J. Tseren', email: 'it@mmc.mn' }, license_count: 3, used_capacity: 516, total_capacity: 600, licensed_product_quantity: 516, usable_license_capacity: 600, overflow_quantity: 0, next_expiry: '2028-02-12', status: 'active' },
  ],
}

export const adminOrganizationDetailFixture: AdminOrganizationLicenseDetail = {
  organization: { id: 1, name: 'Digital PTT Aldarsoft', owner: { name: 'Client Local', email: 'client@digitalptt.local' }, license_manager_count: 2 },
  summary: { subscription_starts_on: '2026-08-18', subscription_expires_on: '2027-08-17', licensed_product_count: 4, active_quantity: 63, usable_license_capacity: 400, overflow_quantity: 0, status: 'expiring_soon' },
  licenses: [clientLicenseDetailFixture, { ...clientLicenseDetailFixture, license_number: 'LIC-RA-01509', name: 'RadioAdmin License 02', capacity: 200, used_capacity: 50, available_capacity: 150, starts_on: '2027-03-04', expires_on: '2028-03-03', renews_on: '2028-03-04', remaining_days: 562, allocations: [] }],
  notifications: { renewal_reminder_scheduled_for: '2027-06-18', renewal_invoice_status: 'not_sent' },
  events: [
    { id: 1, kind: 'provisioned', message: 'Subscription activated and 63 product licenses created.', actor_name: 'Store Administrator', license_number: 'LIC-RA-01482', metadata: {}, created_at: '2026-08-18T09:30:00Z' },
    { id: 2, kind: 'notification_sent', message: 'Renewal invoice sent to organization owner.', actor_name: 'Store Administrator', license_number: null, metadata: {}, created_at: '2026-08-17T09:30:00Z' },
    { id: 3, kind: 'provisioned', message: 'Organization created and Client Local made owner.', actor_name: 'Client Local', license_number: null, metadata: {}, created_at: '2025-08-18T09:30:00Z' },
  ],
  permissions: { can_adjust: true, can_send_renewal_invoice: true, can_send_notification: true },
}
