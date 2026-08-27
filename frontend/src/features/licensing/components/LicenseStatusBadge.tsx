import type { OrganizationLicenseStatus } from '../types'

const statusStyles: Record<OrganizationLicenseStatus, string> = {
  active: 'bg-success-soft text-success',
  expiring_soon: 'bg-warning-soft text-warning',
  pending_payment: 'bg-brand-soft text-brand',
  expired: 'bg-danger-soft text-danger',
  cancelled: 'bg-surface-muted text-muted',
  draft: 'bg-surface-muted text-muted',
  no_licenses: 'bg-surface-muted text-muted',
}

export function LicenseStatusBadge({ status }: { status: OrganizationLicenseStatus }) {
  return <span className={`inline-flex min-h-7 items-center rounded-full px-3 text-xs font-bold capitalize ${statusStyles[status]}`}>{status.replaceAll('_', ' ')}</span>
}
