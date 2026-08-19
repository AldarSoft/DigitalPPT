import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, Bell, CalendarDays, CreditCard, SlidersHorizontal, Users } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../../../lib/api'
import { tw } from '../../../lib/tailwind-styles'
import { LicenseStatusBadge } from '../components/LicenseStatusBadge'
import { adminOrganizationDetailFixture } from '../fixtures'
import { licensingKeys } from '../queryKeys'

export function AdminLicenseDetailPage() {
  const organizationId = Number(useParams().organizationId)
  const detailQuery = useQuery({
    queryKey: licensingKeys.adminOrganization(organizationId),
    queryFn: () => api.adminLicenseOrganization(organizationId),
    enabled: Number.isInteger(organizationId) && organizationId > 0,
    placeholderData: adminOrganizationDetailFixture,
  })
  const detail = detailQuery.data

  return (
    <main className={tw('admin-page')}>
      <Link className="mb-4 inline-flex items-center gap-2 font-bold text-primary hover:underline" to="/admin/licenses"><ArrowLeft size={18} />Back to license management</Link>
      <div className={tw('admin-title-row')}>
        <div><p className={tw('admin-breadcrumb')}>Workspace / License management / Organization</p><h1>{detail?.organization.name ?? 'Organization license details'}</h1><p>Organization license details · {detail?.organization.owner?.name ?? 'No owner'} is the Organization Owner</p></div>
        {detail ? <LicenseStatusBadge status={detail.summary.status} /> : null}
      </div>
      {detailQuery.isError || !Number.isInteger(organizationId) ? <p className="mb-3 rounded-control bg-danger-soft px-3 py-2 text-sm text-danger">Live organization data could not be loaded. Showing the approved page shell.</p> : null}
      {detail ? (
        <div className="grid gap-4">
          <section className="grid gap-3 md:grid-cols-3">
            <SummaryCard icon={CalendarDays} label="Subscription" value={`${formatDate(detail.summary.subscription_starts_on)} – ${formatDate(detail.summary.subscription_expires_on)}`} note="Annual subscription" />
            <SummaryCard icon={Users} label="Organization control" value={`${detail.organization.owner ? 1 : 0} Owner · ${detail.organization.license_manager_count} License Managers`} note={detail.organization.owner ? `${detail.organization.owner.name} · ${detail.organization.owner.email}` : 'No owner'} />
            <SummaryCard icon={CreditCard} label="Licensed products" value={`${detail.summary.licensed_product_count} products · ${detail.summary.active_quantity} active product licenses`} note="Current licensed quantity" />
          </section>
          <div className="grid items-start gap-4 xl:grid-cols-[minmax(0,1.45fr)_minmax(280px,.7fr)]">
            <section className={tw('admin-panel admin-table-wrap')}>
              <div className="flex items-center justify-between gap-3 px-4 py-3"><h2 className="text-xl">Product licenses</h2><button className="border-0 bg-transparent text-sm font-bold text-brand" type="button">Edit quantities</button></div>
              <table className={tw('admin-table admin-table-compact')}><thead><tr><th>License</th><th>Purchased</th><th>Active</th><th>Expiry</th></tr></thead><tbody>{detail.licenses.map((license) => <tr key={license.license_number}><td><strong className="block">{license.name}</strong><span className="text-[11px] text-muted">{license.license_number}</span></td><td>{license.capacity}</td><td>{license.used_capacity}</td><td>{formatDate(license.expires_on)}</td></tr>)}</tbody></table>
            </section>
            <aside className={tw('admin-panel')}>
              <h2 className="text-xl">Support and notifications</h2>
              <Action icon={Bell} title="Renewal reminder" note={detail.notifications.renewal_reminder_scheduled_for ? `Scheduled for ${formatDate(detail.notifications.renewal_reminder_scheduled_for)}` : 'Not scheduled'} action="View" />
              <Action icon={CreditCard} title="Renewal invoice" note={detail.notifications.renewal_invoice_status.replaceAll('_', ' ')} action="Send invoice" />
              <Action icon={SlidersHorizontal} title="Manual adjustment" note="No outstanding adjustments" action="Adjust" />
            </aside>
          </div>
          <section className={tw('admin-panel')}><h2 className="text-xl">License history</h2><ol className="mt-3 grid gap-0">{detail.events.map((event) => <li className="grid gap-2 border-t border-border py-4 first:border-t-0 md:grid-cols-[130px_14px_minmax(0,1fr)] md:gap-4" key={event.id}><time className="text-xs font-bold text-muted">{formatDate(event.created_at)}</time><span className="mt-1 hidden size-2 rounded-full bg-brand md:block" /><div><strong className="block text-sm">{event.message}</strong><span className="text-xs text-muted">{event.actor_name}</span></div></li>)}</ol></section>
        </div>
      ) : null}
    </main>
  )
}

function SummaryCard({ icon: Icon, label, value, note }: { icon: typeof CalendarDays; label: string; value: string; note: string }) {
  return <article className={tw('admin-panel')}><div className="flex items-center justify-between gap-3"><span className="text-xs font-bold text-muted">{label}</span><Icon className="text-brand" size={19} /></div><strong className="mt-3 block text-base">{value}</strong><span className="mt-2 block text-xs capitalize text-muted">{note}</span></article>
}

function Action({ icon: Icon, title, note, action }: { icon: typeof Bell; title: string; note: string; action: string }) {
  return <div className="grid grid-cols-[24px_minmax(0,1fr)_auto] gap-3 border-b border-border py-4 last:border-b-0"><Icon className="mt-0.5 text-muted" size={20} /><div><strong className="block text-sm">{title}</strong><span className="mt-1 block text-xs capitalize text-muted">{note}</span></div><button className="border-0 bg-transparent text-xs font-bold text-brand" type="button">{action}</button></div>
}

function formatDate(value: string | null) {
  return value ? new Intl.DateTimeFormat('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }).format(new Date(value)) : 'Not set'
}
