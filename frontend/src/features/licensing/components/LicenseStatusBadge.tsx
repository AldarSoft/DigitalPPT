import type { LicenseStatus } from '../types'

const statusStyles: Record<LicenseStatus, string> = {
  active: 'bg-success-soft text-success',
  expiring_soon: 'bg-warning-soft text-warning',
  pending_payment: 'bg-brand-soft text-brand',
  expired: 'bg-danger-soft text-danger',
  cancelled: 'bg-surface-muted text-muted',
}

export function LicenseStatusBadge({ status }: { status: LicenseStatus }) {
  return <span className={`inline-flex min-h-7 items-center rounded-full px-3 text-xs font-bold capitalize ${statusStyles[status]}`}>{status.replaceAll('_', ' ')}</span>
}
