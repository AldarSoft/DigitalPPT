import { useQuery } from '@tanstack/react-query'
import { CalendarDays, Info, KeyRound } from 'lucide-react'
import { useSearchParams } from 'react-router-dom'
import { api } from '../../../lib/api'
import { LicenseStatusBadge } from '../components/LicenseStatusBadge'
import { clientLicenseDetailFixture, clientLicenseListFixture } from '../fixtures'
import { licensingKeys } from '../queryKeys'

export function OrganizationLicensesPanel() {
  const [searchParams, setSearchParams] = useSearchParams()
  const licensesQuery = useQuery({ queryKey: licensingKeys.licenses(), queryFn: api.organizationLicenses, placeholderData: clientLicenseListFixture })
  const licenses = licensesQuery.data?.licenses ?? []
  const selectedNumber = searchParams.get('license') ?? licenses[0]?.license_number ?? ''
  const selectedListItem = licenses.find((license) => license.license_number === selectedNumber) ?? licenses[0]
  const detailPlaceholder = selectedListItem ? { ...clientLicenseDetailFixture, ...selectedListItem, subscription: { ...clientLicenseDetailFixture.subscription, starts_on: selectedListItem.starts_on, expires_on: selectedListItem.expires_on, renews_on: selectedListItem.renews_on, remaining_days: selectedListItem.remaining_days } } : undefined
  const detailQuery = useQuery({ queryKey: licensingKeys.license(selectedNumber), queryFn: () => api.organizationLicense(selectedNumber), enabled: Boolean(selectedNumber), placeholderData: detailPlaceholder })
  const detail = detailQuery.data

  const selectLicense = (licenseNumber: string) => {
    const next = new URLSearchParams(searchParams)
    next.set('tab', 'licenses')
    next.set('license', licenseNumber)
    setSearchParams(next, { replace: true })
  }

  return (
    <div className="grid gap-4">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div><h2 className="text-[28px] leading-tight">Organization licenses</h2><p className="mt-1 text-sm text-muted">View your organization&apos;s product license capacity and renewal dates.</p></div>
        <span className="inline-flex items-center gap-2 rounded-control bg-surface-muted px-3 py-2 text-xs font-bold text-muted"><KeyRound size={17} className="text-brand" />Owner &amp; License Manager access</span>
      </header>
      <div className="flex items-start gap-3 rounded-panel border border-[#bfd5f5] bg-info-soft px-4 py-3 text-sm text-[#244368]"><Info className="mt-0.5 shrink-0 text-brand" size={19} /><p>Each license supports its configured radio-product capacity. Select a license to review linked products and source orders.</p></div>
      {licensesQuery.isError ? <p className="rounded-control bg-danger-soft px-3 py-2 text-sm text-danger">Live license data could not be loaded. Showing the approved page shell.</p> : null}
      <div className="grid items-start gap-4 xl:grid-cols-[minmax(0,1.35fr)_minmax(290px,.75fr)]">
        <section className="min-w-0 rounded-panel border border-border bg-white p-5">
          <div className="mb-4 flex items-center justify-between gap-3"><h3 className="text-xl">Your licenses</h3><strong className="text-sm text-success">{licensesQuery.data?.summary.active_license_count ?? 0} active licenses</strong></div>
          <div className="hidden grid-cols-[minmax(0,1.2fr)_minmax(130px,.8fr)_minmax(120px,.6fr)_84px] gap-4 bg-surface-raised px-3 py-2.5 text-xs font-bold text-muted md:grid"><span>License</span><span>Products</span><span>Expires</span><span /></div>
          {licenses.map((license) => {
            const selected = license.license_number === selectedNumber
            return <article aria-current={selected ? 'true' : undefined} className={`grid gap-4 border-b border-border px-3 py-5 last:border-b-0 md:grid-cols-[minmax(0,1.2fr)_minmax(130px,.8fr)_minmax(120px,.6fr)_84px] md:items-center ${selected ? 'rounded-control bg-info-soft ring-1 ring-[#bdd4f5]' : ''}`} key={license.id}>
              <div className="min-w-0"><strong className="block truncate">{license.name}</strong><span className="text-xs text-muted">{license.license_number}</span></div>
              <div><strong>{license.used_capacity} / {license.capacity}</strong><div className="mt-2 h-2 overflow-hidden rounded-full bg-border" role="progressbar" aria-label={`${license.name} capacity`} aria-valuemin={0} aria-valuemax={license.capacity} aria-valuenow={license.used_capacity}><span className="block h-full rounded-full bg-brand" style={{ width: `${license.capacity_percentage}%` }} /></div></div>
              <div className="grid justify-items-start gap-2"><strong className="block text-sm">{formatDate(license.expires_on)}</strong><LicenseStatusBadge status={license.status} /></div>
              <button className={`${selected ? '!bg-brand !text-white' : '!bg-brand-soft !text-brand'} inline-flex min-h-9 items-center justify-center rounded-control px-3 text-xs font-bold`} type="button" onClick={() => selectLicense(license.license_number)}>Details</button>
            </article>
          })}
        </section>
        <aside className="min-w-0 rounded-panel border border-border bg-white p-5">
          {detail ? <>
            <div className="flex items-start justify-between gap-3"><div className="min-w-0"><h3 className="truncate text-xl">{detail.name}</h3><p className="mt-1 text-xs text-muted">{detail.license_number}</p></div><LicenseStatusBadge status={detail.status} /></div>
            <div className="mt-5 rounded-panel bg-surface-raised p-4"><div className="flex items-end justify-between gap-3"><strong>Products assigned</strong><b className="text-2xl">{detail.used_capacity} / {detail.capacity}</b></div><div className="mt-3 h-2 overflow-hidden rounded-full bg-border"><span className="block h-full rounded-full bg-success" style={{ width: `${Math.min(100, detail.capacity ? detail.used_capacity / detail.capacity * 100 : 0)}%` }} /></div><p className="mt-3 text-sm font-semibold text-success">{detail.available_capacity === 0 ? 'This license is at full capacity.' : `${detail.available_capacity} product capacity available.`}</p></div>
            <div className="mt-5 border-t border-border pt-4"><div className="flex items-start gap-3"><CalendarDays className="mt-0.5 shrink-0 text-warning" size={20} /><div><strong>Annual subscription</strong><p className="mt-1 text-xs text-muted">{formatDate(detail.subscription.starts_on)} – {formatDate(detail.subscription.expires_on)}</p></div></div><dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-3 text-sm"><div><dt className="text-xs text-muted">Plan</dt><dd className="mt-1 font-semibold">{detail.plan_name}</dd></div><div><dt className="text-xs text-muted">Renewal due</dt><dd className="mt-1 font-semibold">{formatDate(detail.subscription.renews_on)}</dd></div><div><dt className="text-xs text-muted">Term</dt><dd className="mt-1 font-semibold">{detail.subscription.term_days ? `${detail.subscription.term_days} days` : 'Not set'}</dd></div><div><dt className="text-xs text-muted">Source order</dt><dd className="mt-1 font-semibold text-brand">{detail.subscription.source_order?.order_number ?? 'Not available'}</dd></div></dl></div>
            <StatusFeedback status={detail.status} remainingDays={detail.remaining_days} />
          </> : <p>No license selected.</p>}
        </aside>
      </div>
      {detail ? <section className="min-w-0 overflow-hidden rounded-panel border border-border bg-white">
        <div className="flex flex-wrap items-start justify-between gap-3 px-5 py-4"><div><h3 className="text-xl">Assigned radio products</h3><p className="mt-1 text-sm text-muted">Products assigned through completed purchase orders.</p></div><strong className="text-sm text-brand">{detail.used_capacity} products assigned</strong></div>
        {detail.allocations.length ? <div className="overflow-x-auto"><table className="w-full min-w-[680px] border-collapse text-left"><thead className="bg-surface-raised text-xs text-muted"><tr><th className="px-5 py-3">Product</th><th className="px-5 py-3">Source order</th><th className="px-5 py-3">Assigned</th><th className="px-5 py-3">Order date</th></tr></thead><tbody>{detail.allocations.map((allocation) => <tr className="border-t border-border" key={allocation.id}><td className="px-5 py-4"><strong className="block text-sm">{allocation.product.name}</strong><span className="text-xs text-muted">{allocation.product.sku}</span></td><td className="px-5 py-4 text-sm font-bold text-brand">{allocation.source_order.order_number}</td><td className="px-5 py-4 text-sm font-semibold">{allocation.quantity}</td><td className="px-5 py-4 text-sm text-muted">{formatDate(allocation.source_order.ordered_at)}</td></tr>)}</tbody></table></div> : <p className="border-t border-border px-5 py-8 text-center text-sm text-muted">No products are assigned to this license yet.</p>}
      </section> : null}
    </div>
  )
}

function StatusFeedback({ status, remainingDays }: { status: 'pending_payment' | 'active' | 'expiring_soon' | 'expired' | 'cancelled'; remainingDays: number | null }) {
  const feedback = {
    active: { tone: 'bg-success-soft text-success', text: remainingDays === null ? 'License is active.' : `License is active with ${remainingDays} days remaining.` },
    expiring_soon: { tone: 'bg-warning-soft text-warning', text: remainingDays === null ? 'Renewal is due soon.' : `Renewal is due in ${remainingDays} days.` },
    pending_payment: { tone: 'bg-brand-soft text-brand', text: 'License activation is waiting for payment confirmation.' },
    expired: { tone: 'bg-danger-soft text-danger', text: 'This license has expired. Contact Digital PTT to renew it.' },
    cancelled: { tone: 'bg-surface-muted text-muted', text: 'This license is cancelled.' },
  }[status]
  return <p className={`mt-5 rounded-control px-3 py-2.5 text-sm font-semibold ${feedback.tone}`}>{feedback.text}</p>
}

function formatDate(value: string | null) {
  return value ? new Intl.DateTimeFormat('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }).format(new Date(value)) : 'Not set'
}
