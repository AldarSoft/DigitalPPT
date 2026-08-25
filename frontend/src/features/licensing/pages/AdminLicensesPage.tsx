import { useDeferredValue, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, CheckCircle2, ChevronDown, Clock3, CreditCard, KeyRound, LoaderCircle, Search, ShieldCheck, X } from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'
import { ApiError, api, unwrap } from '../../../lib/api'
import { tw } from '../../../lib/tailwind-styles'
import { licensingKeys } from '../queryKeys'
import type { AdminLicenseFilters } from '../types'
import { LicenseStatusBadge } from '../components/LicenseStatusBadge'

export function AdminLicensesPage() {
  const navigate = useNavigate()
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState<AdminLicenseFilters['status']>('')
  const [product, setProduct] = useState('')
  const deferredSearch = useDeferredValue(search.trim())
  const filters: AdminLicenseFilters = { search: deferredSearch, status, product, page: 1, page_size: 25 }
  const productsQuery = useQuery({
    queryKey: licensingKeys.licenseProducts(),
    queryFn: () => api.products('licensing_role=license_product&status=published&page_size=100'),
  })
  const licenseProducts = productsQuery.data ? unwrap(productsQuery.data) : []
  const organizationsQuery = useQuery({
    queryKey: licensingKeys.adminOrganizations(filters),
    queryFn: () => api.adminLicenseOrganizations(filters),
    placeholderData: (previous) => previous,
  })
  const summary = organizationsQuery.data?.summary
  const accessDenied = organizationsQuery.error instanceof ApiError && [401, 403].includes(organizationsQuery.error.status)

  return (
    <main className={tw('admin-page')}>
      <div className={tw('admin-title-row')}>
        <div><p className={tw('admin-breadcrumb')}>Workspace / License management</p><h1>Organizations</h1><p>Review licenses, product capacity and renewal dates.</p></div>
      </div>
      {organizationsQuery.isLoading ? <AdminState icon={<LoaderCircle className="animate-spin text-brand" size={22} />} title="Loading organizations" text="Retrieving organization licenses, capacity, and renewal status." /> : null}
      {accessDenied ? <AdminState icon={<ShieldCheck className="text-warning" size={22} />} title="License Management access is required" text="Only Digital PTT administrators can review organization licenses." /> : null}
      {organizationsQuery.isError && !accessDenied ? <AdminState icon={<AlertTriangle className="text-danger" size={22} />} title="Organizations could not be loaded" text={errorMessage(organizationsQuery.error)} action={<button className="min-h-9 rounded-control border border-border-input bg-white px-3 text-xs font-bold text-brand" type="button" onClick={() => void organizationsQuery.refetch()}>Try again</button>} /> : null}
      {summary ? (
        <section className="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-4" aria-label="License summary">
          <Summary icon={KeyRound} label="Organizations with licenses" value={summary.organizations_with_licenses} />
          <Summary icon={CheckCircle2} label="Active organization licenses" value={summary.active_licenses} tone="success" />
          <Summary icon={Clock3} label="Licenses expiring in 60 days" value={summary.licenses_expiring_in_60_days} tone="warning" />
          <Summary icon={CreditCard} label="Payment review" value={summary.payments_in_review} tone="danger" />
        </section>
      ) : null}
      {!organizationsQuery.isLoading && !organizationsQuery.isError ? <><section className={tw('admin-toolbar')}>
        <div><Search size={19} /><input aria-label="Search organizations" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search organization" /></div>
        <label className={tw('admin-select')}><select aria-label="Filter license status" value={status} onChange={(event) => setStatus(event.target.value as AdminLicenseFilters['status'])}><option value="">All license statuses</option><option value="active">Active</option><option value="expiring_soon">Expiring soon</option><option value="pending_payment">Pending payment</option><option value="expired">Expired</option><option value="cancelled">Cancelled</option></select><ChevronDown size={16} /></label>
        <label className={tw('admin-select')}><select aria-label="Filter license product" value={product} onChange={(event) => setProduct(event.target.value)}><option value="">All products</option>{licenseProducts.map((item) => <option value={item.sku} key={item.id}>{item.name}</option>)}</select><ChevronDown size={16} /></label>
        {search || status || product ? <button type="button" onClick={() => { setSearch(''); setStatus(''); setProduct('') }}><X size={16} />Clear</button> : null}
      </section>
      <section className={tw('admin-panel admin-table-wrap')}>
        {organizationsQuery.isFetching ? <div className="h-0.5 w-full overflow-hidden bg-brand-soft"><span className="block h-full w-1/3 animate-pulse bg-brand" /></div> : null}
        {organizationsQuery.data?.results.length ? <table className={tw('admin-table')}><thead><tr><th>Organization</th><th>Licenses</th><th>Product capacity</th><th>Next expiry</th><th>Status</th><th>Open</th></tr></thead><tbody>{organizationsQuery.data.results.map((organization) => {
          const destination = `/admin/licenses/${organization.id}`
          return <tr className="cursor-pointer focus-visible:bg-info-soft focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-brand" key={organization.id} tabIndex={0} role="link" aria-label={`Open ${organization.name} license details`} onClick={() => navigate(destination)} onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); navigate(destination) } }}><td><strong className="block">{organization.name}</strong><span className="text-[11px] text-muted">{organization.owner ? `${organization.owner.name} · ${organization.owner.email}` : 'No organization owner'}</span></td><td>{organization.license_count}</td><td>{organization.used_capacity} / {organization.total_capacity}</td><td>{formatDate(organization.next_expiry)}</td><td><LicenseStatusBadge status={organization.status} /></td><td><Link className="font-bold text-brand hover:underline" to={destination}>Open</Link></td></tr>
        })}</tbody></table> : <div className={tw('admin-empty-row')}><KeyRound size={26} /><strong>No organizations found</strong><span>Try changing the search or license filters.</span></div>}
      </section></> : null}
    </main>
  )
}

function Summary({ icon: Icon, label, value, tone = 'brand' }: { icon: typeof KeyRound; label: string; value: number; tone?: 'brand' | 'success' | 'warning' | 'danger' }) {
  const color = { brand: 'text-brand', success: 'text-success', warning: 'text-warning', danger: 'text-danger' }[tone]
  return <article className={tw('admin-panel')}><div className="flex items-start justify-between gap-3"><span className="text-xs font-semibold text-muted">{label}</span><Icon className={color} size={20} /></div><strong className="mt-3 block text-2xl">{value.toLocaleString()}</strong></article>
}

function formatDate(value: string | null) {
  return value ? new Intl.DateTimeFormat('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }).format(new Date(value)) : 'Not set'
}

function AdminState({ icon, title, text, action }: { icon: React.ReactNode; title: string; text: string; action?: React.ReactNode }) {
  return <section className="mb-4 flex items-start gap-3 rounded-panel border border-border bg-white px-5 py-4"><span className="mt-0.5 shrink-0">{icon}</span><div><h2 className="text-base">{title}</h2><p className="mt-1 text-sm text-muted">{text}</p>{action ? <div className="mt-3">{action}</div> : null}</div></section>
}

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : 'Please try again.'
}
