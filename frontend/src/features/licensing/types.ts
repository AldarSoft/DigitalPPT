export type LicenseStatus = 'draft' | 'pending_payment' | 'active' | 'expiring_soon' | 'expired' | 'cancelled'
export type OrganizationLicenseStatus = LicenseStatus | 'no_licenses'
export type OrganizationRole = 'owner' | 'license_manager'
export type OrganizationStatus = 'draft' | 'active' | 'inactive'

export interface OrganizationSettings {
  id: number
  name: string
  billing_email: string
  status: OrganizationStatus
}

export interface AdminOrganizationCreateInput {
  name: string
  billing_email?: string
  owner_mode: 'existing' | 'create_account' | 'invite' | 'draft'
  existing_owner_id?: number
  owner_email?: string
  owner_first_name?: string
  owner_last_name?: string
  owner_phone?: string
}

export interface AdminOrganizationCreateResponse {
  id: number
  name: string
  billing_email: string
  status: OrganizationStatus
  owner: { name: string; email: string } | null
  invitation: OrganizationInvitation | null
  setup_url: string | null
}

export interface OrganizationLicenseSummary {
  license_count: number
  active_license_count: number
  expiring_soon_count: number
  expired_license_count: number
  total_capacity: number
  used_capacity: number
  available_capacity: number
  next_expiry: string | null
  next_expiry_remaining_days: number | null
}

export interface OrganizationSummaryResponse {
  organization: { id: number; public_id: string; name: string; billing_email: string; current_user_role: OrganizationRole }
  summary: OrganizationLicenseSummary
  team: { owner: { name: string; email: string } | null; license_manager_count: number; pending_invitation_count: number }
}

export interface SourceOrder { order_number: string; ordered_at: string }

export interface ClientLicenseListItem {
  id: number
  license_number: string
  name: string
  plan_name: string
  plan_sku: string
  status: LicenseStatus
  capacity: number
  used_capacity: number
  available_capacity: number
  capacity_percentage: number
  starts_on: string | null
  expires_on: string | null
  renews_on: string | null
  remaining_days: number | null
}

export interface ClientLicenseListResponse {
  organization: { id: number; public_id: string; name: string; role: OrganizationRole }
  summary: OrganizationLicenseSummary
  licenses: ClientLicenseListItem[]
  renewal_request: { issued: boolean; issued_at: string | null }
}

export interface ClientLicenseDetail {
  license_number: string
  name: string
  plan_name: string
  plan_sku: string
  status: LicenseStatus
  capacity: number
  used_capacity: number
  available_capacity: number
  starts_on: string | null
  expires_on: string | null
  renews_on: string | null
  remaining_days: number | null
  subscription: { term_days: number | null; starts_on: string | null; expires_on: string | null; renews_on: string | null; remaining_days: number | null; source_order: SourceOrder | null }
  allocations: Array<{ id: number; product: { id: number; name: string; sku: string }; quantity: number; source_order: SourceOrder }>
}

export interface LicenseRenewalSummary {
  license_number: string
  license_name: string
  organization_id: number
  organization_name: string
  current_expires_on: string | null
  projected_expires_on: string
  term_days: number
  product_id: number
  product_name: string
  product_sku: string
  product_image_url: string
  amount: string
}

export interface OrganizationInvitation {
  invitation_id: number
  email: string
  role: 'owner' | 'license_manager'
  status: string
  expires_at: string
  accept_url?: string
}

export interface OrganizationInvitationAcceptance {
  organization_id: number
  organization_name: string
  role: 'owner' | 'license_manager'
}

export interface OrganizationWorkspace {
  id: number
  name: string
  role: 'owner' | 'license_manager'
}

export interface OrganizationWorkspaceListResponse {
  organizations: OrganizationWorkspace[]
  default_organization_id: number | null
}

export interface OrganizationCreateInput {
  name: string
  billing_email?: string
}

export interface OrganizationTeamResponse {
  organization: { id: number; name: string }
  current_user_role: OrganizationRole
  owner: { id: number; name: string; email: string } | null
  license_managers: Array<{ membership_id: number; name: string; email: string; role: 'license_manager'; status: 'active' }>
  pending_invitations: OrganizationInvitation[]
  permissions: { can_invite: boolean; can_revoke_manager: boolean; can_transfer_ownership: boolean }
}

export interface AdminLicenseFilters {
  search?: string
  status?: LicenseStatus | ''
  product?: string
  customer_id?: number
  page?: number
  page_size?: number
}

export interface AdminOrganizationLicenseListResponse {
  summary: { organizations_with_licenses: number; active_licenses: number; licenses_expiring_in_60_days: number; payments_in_review: number }
  count: number
  next: string | null
  previous: string | null
  results: Array<{ id: number; name: string; owner: { name: string; email: string } | null; license_count: number; used_capacity: number; total_capacity: number; next_expiry: string | null; status: OrganizationLicenseStatus }>
}

export interface AdminLicenseEvent {
  id: number
  kind: string
  message: string
  actor_name: string
  license_number: string | null
  metadata: Record<string, unknown>
  created_at: string
}

export interface AdminOrganizationLicenseDetail {
  organization: { id: number; name: string; owner: { name: string; email: string } | null; license_manager_count: number }
  summary: { subscription_starts_on: string | null; subscription_expires_on: string | null; licensed_product_count: number; active_quantity: number; status: OrganizationLicenseStatus }
  licenses: ClientLicenseDetail[]
  notifications: { renewal_reminder_scheduled_for: string | null; renewal_invoice_status: string }
  events: AdminLicenseEvent[]
  permissions: { can_adjust: boolean; can_send_renewal_invoice: boolean; can_send_notification: boolean }
}

export interface AdminOrganizationUsers {
  organization: { id: number; name: string }
  owner: { membership_id: number; user_id: number; name: string; email: string; role: 'owner'; status: 'active' } | null
  license_managers: Array<{ membership_id: number; user_id: number; name: string; email: string; role: 'license_manager'; status: 'active' }>
  pending_invitations: OrganizationInvitation[]
}

export interface AdminLicenseEventListResponse {
  count: number
  next: string | null
  previous: string | null
  results: AdminLicenseEvent[]
}

export interface LicenseSummary {
  id: number
  license_number: string
  name: string
  status: LicenseStatus
  capacity: number
  used_capacity: number
  remaining_days: number | null
  starts_on: string | null
  expires_on: string | null
  renews_on: string | null
  organization: number
  license_product: number
}

export interface LicenseAdjustmentInput { capacity?: number; status?: LicenseStatus; reason: string }
export interface OrganizationNotificationInput { title: string; message: string; license_number?: string }
