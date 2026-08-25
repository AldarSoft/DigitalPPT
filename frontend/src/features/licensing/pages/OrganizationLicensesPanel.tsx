import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState, type FormEvent, type ReactNode } from 'react'
import { AlertTriangle, Building2, CalendarDays, CreditCard, Info, KeyRound, LoaderCircle, Plus, RefreshCw, ShieldCheck, X } from 'lucide-react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { toast } from 'sonner'
import { ApiError, api } from '../../../lib/api'
import { tw } from '../../../lib/tailwind-styles'
import { LicenseStatusBadge } from '../components/LicenseStatusBadge'
import { licensingKeys } from '../queryKeys'
import type { ClientLicenseDetail } from '../types'

export function OrganizationLicensesPanel({ organizationId, workspaceLoading, workspaceError, onWorkspaceRetry }: { organizationId: number | null; workspaceLoading: boolean; workspaceError: unknown; onWorkspaceRetry: () => void }) {
  const [searchParams, setSearchParams] = useSearchParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [showCreateForm, setShowCreateForm] = useState(false)
  const [organizationName, setOrganizationName] = useState('')
  const licensesQuery = useQuery({ queryKey: licensingKeys.licenses(organizationId), queryFn: () => api.organizationLicenses(organizationId), enabled: organizationId !== null })
  const licenses = licensesQuery.data?.licenses ?? []
  const hasCurrentRenewalNeed = licenses.some(
    (license) => license.status === 'expiring_soon' || license.status === 'expired',
  )
  const selectedNumber = searchParams.get('license') ?? ''
  const detailQuery = useQuery({ queryKey: licensingKeys.license(selectedNumber, organizationId), queryFn: () => api.organizationLicense(selectedNumber, organizationId), enabled: Boolean(selectedNumber && organizationId !== null) })
  const detail = detailQuery.data
  const permissionDenied = isPermissionDenied(licensesQuery.error) || isPermissionDenied(detailQuery.error)
  const renewalMutation = useMutation({
    mutationFn: (licenseNumber: string) => api.licenseRenewalSummary(licenseNumber, organizationId),
    onSuccess: (renewal) => navigate(`/payment?renewal_license=${encodeURIComponent(renewal.license_number)}&org=${renewal.organization_id}`),
    onError: (error) => toast.error(errorMessage(error)),
  })
  const createOrganizationMutation = useMutation({
    mutationFn: api.createOrganization,
    onSuccess: (workspaces) => {
      queryClient.setQueryData(licensingKeys.workspaces(), workspaces)
      const createdOrganizationId = workspaces.default_organization_id
      if (createdOrganizationId) {
        navigate(`/account?tab=licenses&org=${createdOrganizationId}`, { replace: true })
      }
      toast.success('Organization created')
    },
    onError: (error) => toast.error(errorMessage(error)),
  })

  const createOrganization = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const name = organizationName.trim()
    if (!name) return
    createOrganizationMutation.mutate({ name })
  }

  const selectLicense = (licenseNumber: string) => {
    const next = new URLSearchParams(searchParams)
    next.set('tab', 'licenses')
    next.set('license', licenseNumber)
    setSearchParams(next, { replace: true })
  }

  const closeDetails = () => {
    const next = new URLSearchParams(searchParams)
    next.delete('license')
    setSearchParams(next, { replace: true })
  }

  if (organizationId === null && (workspaceLoading || workspaceError)) {
    return <div className="grid gap-4">
      <header className="min-w-0">
        <h2 className="text-[28px] leading-tight max-[480px]:text-[25px]">Licenses</h2>
        <p className="mt-1 text-sm text-muted">Manage your organization&apos;s product licenses and renewal dates.</p>
      </header>
      {workspaceLoading ? <StatePanel icon={<LoaderCircle className="animate-spin text-brand" size={22} />} title="Loading organization access" text="Checking the organizations available to your account." /> : <StatePanel icon={<AlertTriangle className="text-danger" size={22} />} title="Organization access could not be loaded" text={errorMessage(workspaceError)} action={<RetryButton onClick={onWorkspaceRetry} />} />}
    </div>
  }

  if (organizationId === null) {
    return <div className="grid gap-4">
      <header className="min-w-0">
        <h2 className="text-[28px] leading-tight max-[480px]:text-[25px]">Licenses</h2>
        <p className="mt-1 text-sm text-muted">Create an organization before purchasing and managing product licenses.</p>
      </header>
      <section className="grid min-h-[320px] place-items-center rounded-panel border border-border bg-white px-5 py-10 text-center max-[560px]:min-h-[280px] max-[560px]:px-4">
        <div className="w-full max-w-md">
          <span className="mx-auto grid size-12 place-items-center rounded-control bg-brand-soft text-brand"><Building2 size={23} /></span>
          <h3 className="mt-4 text-xl">Create your organization</h3>
          <p className="mx-auto mt-2 max-w-sm text-sm leading-6 text-muted">Your organization will own its licenses, orders, and billing access. You will become its Owner.</p>
          {!showCreateForm ? <button className={tw('action-button action-button-primary mt-5')} type="button" onClick={() => setShowCreateForm(true)}><Plus size={17} />Create organization</button> : <form className="mx-auto mt-5 grid max-w-sm gap-3 text-left" onSubmit={createOrganization}>
            <label className="grid gap-1.5 text-sm font-bold" htmlFor="new-organization-name">Organization name<input autoFocus className="min-h-11 rounded-control border border-border-input bg-white px-3 text-sm font-medium outline-none focus:border-brand focus:ring-2 focus:ring-brand-soft" id="new-organization-name" maxLength={255} placeholder="Company or organization name" required value={organizationName} onChange={(event) => setOrganizationName(event.target.value)} /></label>
            {createOrganizationMutation.isError ? <p className="rounded-control bg-danger-soft px-3 py-2 text-sm text-danger">{errorMessage(createOrganizationMutation.error)}</p> : null}
            <div className="flex flex-wrap justify-end gap-2">
              <button className={tw('action-button action-button-secondary action-button-compact')} type="button" disabled={createOrganizationMutation.isPending} onClick={() => { setShowCreateForm(false); setOrganizationName('') }}>Cancel</button>
              <button className={tw('action-button action-button-primary action-button-compact')} type="submit" disabled={createOrganizationMutation.isPending || !organizationName.trim()}>{createOrganizationMutation.isPending ? <LoaderCircle className="animate-spin" size={16} /> : <Plus size={16} />}{createOrganizationMutation.isPending ? 'Creating...' : 'Create organization'}</button>
            </div>
          </form>}
        </div>
      </section>
    </div>
  }

  return (
    <div className="grid gap-4">
      <header className="grid min-w-0 gap-3 min-[680px]:grid-cols-[minmax(0,1fr)_auto] min-[680px]:items-start">
        <div className="min-w-0"><h2 className="text-[28px] leading-tight max-[480px]:text-[25px]">Organization licenses</h2><p className="mt-1 text-sm text-muted">View your organization&apos;s product license capacity and renewal dates.</p></div>
        <span className="inline-flex w-fit max-w-full items-center gap-2 rounded-control bg-surface-muted px-3 py-2 text-xs font-bold text-muted"><KeyRound size={17} className="shrink-0 text-brand" />Owner &amp; License Manager access</span>
      </header>
      <div className="flex items-start gap-3 rounded-panel border border-[#bfd5f5] bg-info-soft px-4 py-3 text-sm text-[#244368]"><Info className="mt-0.5 shrink-0 text-brand" size={19} /><p>Each license supports its configured radio-product capacity. Select a license to review linked products and source orders.</p></div>
      {licensesQuery.data?.renewal_request?.issued && hasCurrentRenewalNeed ? <div className="flex items-start gap-3 rounded-panel border border-[#f1d29a] bg-warning-soft px-4 py-3 text-sm text-warning"><CalendarDays className="mt-0.5 shrink-0" size={19} /><div><strong className="block">Renewal reminder received</strong><p className="mt-1">Review the applicable license below and select <strong>Extend license</strong> to prepare its payment. Digital PTT support is available when you need assistance.</p></div></div> : null}
      {licensesQuery.isLoading ? <StatePanel icon={<LoaderCircle className="animate-spin text-brand" size={22} />} title="Loading organization licenses" text="Retrieving capacity, expiry, and subscription information." /> : null}
      {permissionDenied ? <StatePanel icon={<ShieldCheck className="text-warning" size={22} />} title="Organization license access is required" text="Only the Organization Owner and invited License Managers can view this page." /> : null}
      {licensesQuery.isError && !permissionDenied ? <StatePanel icon={<AlertTriangle className="text-danger" size={22} />} title="Licenses could not be loaded" text={errorMessage(licensesQuery.error)} action={<RetryButton onClick={() => void licensesQuery.refetch()} />} /> : null}
      {!licensesQuery.isLoading && !licensesQuery.isError && licenses.length === 0 ? <StatePanel icon={<KeyRound className="text-brand" size={22} />} title="No licenses yet" text="Your completed purchase will create or extend an organization license. It will appear here after payment is confirmed." /> : null}
      {!licensesQuery.isLoading && !licensesQuery.isError && !permissionDenied && licenses.length > 0 ? <>
      <div className="grid items-start gap-4">
        <section className="min-w-0 rounded-panel border border-border bg-white p-5 max-[560px]:p-4">
          <div className="mb-4 flex items-center justify-between gap-3 max-[420px]:items-start max-[420px]:flex-col"><h3 className="text-xl">Your licenses</h3><strong className="text-sm text-success">{licensesQuery.data?.summary.active_license_count ?? 0} active licenses</strong></div>
          <div className="hidden grid-cols-[minmax(0,1.2fr)_minmax(120px,.8fr)_minmax(112px,.6fr)_92px] gap-3 bg-surface-raised px-3 py-2.5 text-xs font-bold text-muted min-[680px]:grid"><span>License</span><span>Products</span><span>Expires</span><span /></div>
          {licenses.map((license) => {
            const selected = license.license_number === selectedNumber
            return <article aria-current={selected ? 'true' : undefined} className={`grid min-w-0 gap-4 border-b border-border px-3 py-5 last:border-b-0 min-[460px]:grid-cols-2 min-[680px]:grid-cols-[minmax(0,1.2fr)_minmax(120px,.8fr)_minmax(112px,.6fr)_92px] min-[680px]:items-center min-[680px]:gap-3 ${selected ? 'rounded-control bg-info-soft ring-1 ring-[#bdd4f5]' : ''}`} key={license.id}>
              <div className="min-w-0 min-[460px]:col-span-2 min-[680px]:col-span-1"><strong className="block truncate">{license.name}</strong><span className="block truncate text-xs text-muted">{license.license_number}</span></div>
              <div className="min-w-0"><span className="mb-1 block text-xs font-bold text-muted min-[680px]:hidden">Product capacity</span><strong>{license.used_capacity} / {license.capacity}</strong><div className="mt-2 h-2 overflow-hidden rounded-full bg-border" role="progressbar" aria-label={`${license.name} capacity`} aria-valuemin={0} aria-valuemax={license.capacity} aria-valuenow={license.used_capacity}><span className="block h-full rounded-full bg-brand" style={{ width: `${license.capacity_percentage}%` }} /></div></div>
              <div className="grid min-w-0 justify-items-start gap-2"><span className="block text-xs font-bold text-muted min-[680px]:hidden">Expires</span><strong className="block whitespace-nowrap text-sm">{formatDate(license.expires_on)}</strong><LicenseStatusBadge status={license.status} /></div>
              <button className={tw(`table-action ${selected ? '!border-brand !bg-brand !text-white' : ''} max-[459px]:w-full`)} type="button" onClick={() => selectLicense(license.license_number)}>View details</button>
            </article>
          })}
        </section>
      </div>
      {selectedNumber ? <LicenseDetailsDialog detail={detail} error={detailQuery.error} loading={detailQuery.isLoading} renewalPending={renewalMutation.isPending} onRenew={() => renewalMutation.mutate(selectedNumber)} onClose={closeDetails} onRetry={() => void detailQuery.refetch()} /> : null}
      </> : null}
    </div>
  )
}

function LicenseDetailsDialog({ detail, error, loading, renewalPending, onRenew, onClose, onRetry }: { detail: ClientLicenseDetail | undefined; error: unknown; loading: boolean; renewalPending: boolean; onRenew: () => void; onClose: () => void; onRetry: () => void }) {
  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', closeOnEscape)
    return () => window.removeEventListener('keydown', closeOnEscape)
  }, [onClose])

  return <div className="fixed inset-0 z-50 flex items-center justify-center bg-[#09172d]/45 p-4" role="presentation" onMouseDown={onClose}>
    <section aria-labelledby="license-details-title" aria-modal="true" className="max-h-[calc(100vh-32px)] w-full max-w-4xl overflow-y-auto rounded-panel border border-border bg-white shadow-xl" role="dialog" onMouseDown={(event) => event.stopPropagation()}>
      <header className="sticky top-0 z-10 flex items-start justify-between gap-4 border-b border-border bg-white px-5 py-4 max-[560px]:px-4"><div className="min-w-0"><p className="text-xs font-bold tracking-[.12em] text-brand">LICENSE DETAILS</p><h3 className="mt-1 truncate text-xl" id="license-details-title">{detail?.name ?? 'Loading license details'}</h3>{detail ? <p className="mt-1 text-xs text-muted">{detail.license_number}</p> : null}</div><button aria-label="Close license details" className={tw('action-button action-button-secondary action-button-icon')} type="button" onClick={onClose}><X size={21} /></button></header>
      {loading ? <div className="flex min-h-72 items-center justify-center text-sm text-muted"><LoaderCircle className="mr-2 animate-spin text-brand" size={19} />Loading license details...</div> : null}
      {error ? <div className="grid min-h-72 place-items-center px-5 text-center"><div><strong className="block">License details could not be loaded</strong><p className="mt-1 text-sm text-muted">{errorMessage(error)}</p><div className="mt-3"><RetryButton onClick={onRetry} /></div></div></div> : null}
      {detail ? <div className="grid gap-5 p-5 max-[560px]:p-4">
        <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(260px,.72fr)]">
          <div className="rounded-panel bg-surface-raised p-4"><div className="flex items-end justify-between gap-3"><strong>Products assigned</strong><b className="text-2xl">{detail.used_capacity} / {detail.capacity}</b></div><div className="mt-3 h-2 overflow-hidden rounded-full bg-border"><span className="block h-full rounded-full bg-success" style={{ width: `${Math.min(100, detail.capacity ? detail.used_capacity / detail.capacity * 100 : 0)}%` }} /></div><p className="mt-3 text-sm font-semibold text-success">{detail.available_capacity === 0 ? 'This license is at full capacity.' : `${detail.available_capacity} product capacity available.`}</p></div>
          <div className="rounded-panel border border-border p-4"><div className="flex items-start gap-3"><CalendarDays className="mt-0.5 shrink-0 text-warning" size={20} /><div><strong>Annual subscription</strong><p className="mt-1 text-xs text-muted">{formatDate(detail.subscription.starts_on)} – {formatDate(detail.subscription.expires_on)}</p></div></div><dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-3 text-sm max-[420px]:grid-cols-1"><div><dt className="text-xs text-muted">Plan</dt><dd className="mt-1 font-semibold">{detail.plan_name}</dd></div><div><dt className="text-xs text-muted">Renewal due</dt><dd className="mt-1 font-semibold">{formatDate(detail.subscription.renews_on)}</dd></div><div><dt className="text-xs text-muted">Term</dt><dd className="mt-1 font-semibold">{detail.subscription.term_days ? `${detail.subscription.term_days} days` : 'Not set'}</dd></div><div><dt className="text-xs text-muted">Source order</dt><dd className="mt-1 font-semibold text-brand">{detail.subscription.source_order?.order_number ?? 'Not available'}</dd></div></dl>{canExtendLicense(detail) ? <button className={tw('action-button action-button-primary mt-4 w-full')} type="button" disabled={renewalPending} onClick={onRenew}><CreditCard size={17} />{renewalPending ? 'Preparing extension...' : 'Extend license'}</button> : null}</div>
        </div>
        <StatusFeedback status={detail.status} remainingDays={detail.remaining_days} />
        <section className="min-w-0 overflow-hidden rounded-panel border border-border"><div className="flex flex-wrap items-start justify-between gap-3 px-5 py-4 max-[560px]:px-4"><div><h4 className="text-lg">Assigned radio products</h4><p className="mt-1 text-sm text-muted">Products assigned through completed purchase orders.</p></div><strong className="text-sm text-brand">{detail.used_capacity} products assigned</strong></div>{detail.allocations.length ? <div className="overflow-x-auto"><table className="w-full min-w-[680px] border-collapse text-left"><thead className="bg-surface-raised text-xs text-muted"><tr><th className="px-5 py-3">Product</th><th className="px-5 py-3">Source order</th><th className="px-5 py-3">Assigned</th><th className="px-5 py-3">Order date</th></tr></thead><tbody>{detail.allocations.map((allocation) => <tr className="border-t border-border" key={allocation.id}><td className="px-5 py-4"><strong className="block text-sm">{allocation.product.name}</strong><span className="text-xs text-muted">{allocation.product.sku}</span></td><td className="px-5 py-4 text-sm font-bold text-brand">{allocation.source_order.order_number}</td><td className="px-5 py-4 text-sm font-semibold">{allocation.quantity}</td><td className="px-5 py-4 text-sm text-muted">{formatDate(allocation.source_order.ordered_at)}</td></tr>)}</tbody></table></div> : <p className="border-t border-border px-5 py-8 text-center text-sm text-muted">No products are assigned to this license yet.</p>}</section>
      </div> : null}
    </section>
  </div>
}

function StatePanel({ icon, title, text, action }: { icon: ReactNode; title: string; text: string; action?: ReactNode }) {
  return <section className="flex items-start gap-3 rounded-panel border border-border bg-white px-5 py-4"><span className="mt-0.5 shrink-0">{icon}</span><div><h3 className="text-base">{title}</h3><p className="mt-1 text-sm text-muted">{text}</p>{action ? <div className="mt-3">{action}</div> : null}</div></section>
}

function RetryButton({ onClick }: { onClick: () => void }) {
  return <button className={tw('action-button action-button-secondary action-button-compact')} type="button" onClick={onClick}><RefreshCw size={15} />Try again</button>
}

function isPermissionDenied(error: unknown) {
  return error instanceof ApiError && error.status === 403
}

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : 'Please try again.'
}

function StatusFeedback({ status, remainingDays }: { status: 'pending_payment' | 'active' | 'expiring_soon' | 'expired' | 'cancelled'; remainingDays: number | null }) {
  const feedback = {
    active: { tone: 'bg-success-soft text-success', text: remainingDays === null ? 'License is active.' : `License is active with ${remainingDays} days remaining.` },
    expiring_soon: { tone: 'bg-warning-soft text-warning', text: remainingDays === null || remainingDays > 60 ? 'This license is marked for renewal. You can extend it now.' : `Renewal is due in ${remainingDays} days.` },
    pending_payment: { tone: 'bg-brand-soft text-brand', text: 'License activation is waiting for payment confirmation.' },
    expired: { tone: 'bg-danger-soft text-danger', text: 'This license has expired. Extend it to renew the subscription.' },
    cancelled: { tone: 'bg-surface-muted text-muted', text: 'This license is cancelled.' },
  }[status]
  return <p className={`mt-5 rounded-control px-3 py-2.5 text-sm font-semibold ${feedback.tone}`}>{feedback.text}</p>
}

function formatDate(value: string | null) {
  return value ? new Intl.DateTimeFormat('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }).format(new Date(value)) : 'Not set'
}

function canExtendLicense(detail: ClientLicenseDetail) {
  return detail.status === 'expiring_soon' || detail.status === 'expired' || (detail.remaining_days !== null && detail.remaining_days <= 60)
}
