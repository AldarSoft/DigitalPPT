import { useDeferredValue, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, ArrowRight, Building2, CheckCircle2, ChevronDown, Clock3, CreditCard, KeyRound, LoaderCircle, Plus, Search, ShieldCheck, X } from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { ApiError, api, unwrap } from '../../../lib/api'
import { tw } from '../../../lib/tailwind-styles'
import { licensingKeys } from '../queryKeys'
import type { AdminLicenseFilters, AdminOrganizationCreateInput } from '../types'
import { LicenseStatusBadge } from '../components/LicenseStatusBadge'

export function AdminLicensesPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [creating, setCreating] = useState(false)
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
        <button className={tw('action-button action-button-primary')} type="button" onClick={() => setCreating(true)}><Plus size={18} />Add organization</button>
      </div>
      {organizationsQuery.isLoading ? <AdminState icon={<LoaderCircle className="animate-spin text-brand" size={22} />} title="Loading organizations" text="Retrieving organization licenses, capacity, and renewal status." /> : null}
      {accessDenied ? <AdminState icon={<ShieldCheck className="text-warning" size={22} />} title="License Management access is required" text="Only Digital PTT administrators can review organization licenses." /> : null}
      {organizationsQuery.isError && !accessDenied ? <AdminState icon={<AlertTriangle className="text-danger" size={22} />} title="Organizations could not be loaded" text={errorMessage(organizationsQuery.error)} action={<button className="min-h-9 rounded-control border border-border-input bg-white px-3 text-xs font-bold text-brand" type="button" onClick={() => void organizationsQuery.refetch()}>Try again</button>} /> : null}
      {summary ? (
        <section className="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-5" aria-label="License summary">
          <Summary icon={KeyRound} label="Organizations with licenses" value={summary.organizations_with_licenses} />
          <Summary icon={CheckCircle2} label="Active organization licenses" value={summary.active_licenses} tone="success" />
          <Summary icon={Clock3} label="Licenses expiring in 60 days" value={summary.licenses_expiring_in_60_days} tone="warning" />
          <Summary icon={AlertTriangle} label="Needs capacity" value={summary.organizations_needing_capacity} tone="danger" />
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
        {organizationsQuery.data?.results.length ? <table className={tw('admin-table')}><thead><tr><th>Organization</th><th>Licenses</th><th>Radios / usable capacity</th><th>Next expiry</th><th>Status</th><th>Open</th></tr></thead><tbody>{organizationsQuery.data.results.map((organization) => {
          const destination = `/admin/licenses/${organization.id}`
          return <tr className={`cursor-pointer focus-visible:bg-info-soft focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-brand ${organization.overflow_quantity > 0 ? 'bg-danger-soft' : ''}`} key={organization.id} tabIndex={0} role="link" aria-label={`Open ${organization.name} license details`} onClick={() => navigate(destination)} onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); navigate(destination) } }}><td><strong className="block">{organization.name}</strong><span className="text-[11px] text-muted">{organization.owner ? `${organization.owner.name} · ${organization.owner.email}` : 'No organization owner'}</span>{organization.overflow_quantity > 0 ? <span className="mt-1 inline-flex items-center gap-1 text-[11px] font-bold text-danger"><AlertTriangle size={13} />{organization.overflow_quantity} radios need capacity</span> : null}</td><td>{organization.license_count}</td><td>{organization.licensed_product_quantity} / {organization.usable_license_capacity}</td><td>{formatDate(organization.next_expiry)}</td><td><LicenseStatusBadge status={organization.status} /></td><td><Link className={tw('table-action')} to={destination} onClick={(event) => event.stopPropagation()}>Open <ArrowRight size={14} /></Link></td></tr>
        })}</tbody></table> : <div className={tw('admin-empty-row')}><KeyRound size={26} /><strong>No organizations found</strong><span>Try changing the search or license filters.</span></div>}
      </section></> : null}
      {creating ? <CreateOrganizationDialog onClose={() => setCreating(false)} onCreated={(organizationId) => { setCreating(false); queryClient.invalidateQueries({ queryKey: licensingKeys.admin() }); navigate(`/admin/licenses/${organizationId}`) }} /> : null}
    </main>
  )
}

function CreateOrganizationDialog({ onClose, onCreated }: { onClose: () => void; onCreated: (organizationId: number) => void }) {
  const [data, setData] = useState<AdminOrganizationCreateInput>({ name: '', billing_email: '', owner_mode: 'existing' })
  const usersQuery = useQuery({ queryKey: ['admin-organization-owner-options'], queryFn: () => api.users('ordering=first_name&page_size=100') })
  const users = (usersQuery.data ? unwrap(usersQuery.data) : []).filter((user) => user.is_active && !user.is_staff)
  const create = useMutation({
    mutationFn: () => api.createAdminOrganization(data),
    onSuccess: (organization) => {
      if (organization.status === 'draft') toast.success(organization.invitation ? 'Draft organization created and Owner invited' : 'Draft organization created')
      else toast.success(organization.setup_url ? 'Organization and client account created; setup email queued' : 'Organization created')
      onCreated(organization.id)
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : 'Could not create the organization'),
  })
  const update = <K extends keyof AdminOrganizationCreateInput>(key: K, value: AdminOrganizationCreateInput[K]) => setData((current) => ({ ...current, [key]: value }))
  const needsEmail = data.owner_mode === 'create_account' || data.owner_mode === 'invite'
  return <div className="fixed inset-0 z-100 grid place-items-center bg-[rgba(5,17,38,.48)] p-4" role="presentation" onMouseDown={() => { if (!create.isPending) onClose() }}><section className="max-h-[92vh] w-full max-w-2xl overflow-auto rounded-panel border border-border bg-white p-6 shadow-xl" role="dialog" aria-modal="true" aria-labelledby="create-organization-title" onMouseDown={(event) => event.stopPropagation()}>
    <header className="flex items-start justify-between gap-4"><div><p className={tw('eyebrow')}>ORGANIZATION</p><h2 id="create-organization-title" className="text-2xl">Add organization</h2><p className="mt-1 text-sm text-muted">Choose how the first Owner will join.</p></div><button className={tw('action-button action-button-secondary action-button-icon')} type="button" aria-label="Close" onClick={onClose}><X size={20} /></button></header>
    <form className="mt-5 grid gap-4" onSubmit={(event) => { event.preventDefault(); create.mutate() }}>
      <div className="grid gap-4 sm:grid-cols-2"><label className="grid gap-2 text-sm font-bold">Organization name<input className="min-h-11 rounded-control border border-border-input px-3" required value={data.name} onChange={(event) => update('name', event.target.value)} /></label><label className="grid gap-2 text-sm font-bold">Billing email<input className="min-h-11 rounded-control border border-border-input px-3" type="email" value={data.billing_email ?? ''} onChange={(event) => update('billing_email', event.target.value)} /></label></div>
      <fieldset className="grid gap-2"><legend className="mb-2 text-sm font-bold">Owner setup</legend><div className="grid gap-2 sm:grid-cols-2">{([
        ['existing', 'Select existing client', 'Create Active organization now'],
        ['create_account', 'Create client account', 'Send a single-use password setup link'],
        ['invite', 'Invite Owner', 'Keep Draft until invitation is accepted'],
        ['draft', 'Create Draft only', 'No orders, payments, or licenses yet'],
      ] as const).map(([value, label, help]) => <label className={`cursor-pointer rounded-control border p-3 ${data.owner_mode === value ? 'border-brand bg-brand-soft' : 'border-border-input bg-white'}`} key={value}><span className="flex items-center gap-2"><input type="radio" name="owner-mode" value={value} checked={data.owner_mode === value} onChange={() => update('owner_mode', value)} /><strong className="text-sm">{label}</strong></span><small className="mt-1 block pl-6 text-xs text-muted">{help}</small></label>)}</div></fieldset>
      {data.owner_mode === 'existing' ? <label className="grid gap-2 text-sm font-bold">Organization Owner<select className="min-h-11 rounded-control border border-border-input bg-white px-3" required value={data.existing_owner_id ?? ''} onChange={(event) => update('existing_owner_id', Number(event.target.value))}><option value="">Select client account</option>{users.map((user) => <option value={user.id} key={user.id}>{`${user.first_name} ${user.last_name}`.trim() || user.email} - {user.email}</option>)}</select></label> : null}
      {needsEmail ? <div className="grid gap-4 sm:grid-cols-2"><label className="grid gap-2 text-sm font-bold sm:col-span-2">Owner email<input className="min-h-11 rounded-control border border-border-input px-3" type="email" required value={data.owner_email ?? ''} onChange={(event) => update('owner_email', event.target.value)} /></label>{data.owner_mode === 'create_account' ? <><label className="grid gap-2 text-sm font-bold">First name<input className="min-h-11 rounded-control border border-border-input px-3" value={data.owner_first_name ?? ''} onChange={(event) => update('owner_first_name', event.target.value)} /></label><label className="grid gap-2 text-sm font-bold">Last name<input className="min-h-11 rounded-control border border-border-input px-3" value={data.owner_last_name ?? ''} onChange={(event) => update('owner_last_name', event.target.value)} /></label></> : null}</div> : null}
      {data.owner_mode === 'draft' ? <div className="flex items-start gap-3 rounded-control border border-warning bg-warning-soft p-3 text-sm text-warning"><AlertTriangle className="mt-0.5 shrink-0" size={18} /><span>This organization remains blocked until an Owner is assigned or invited.</span></div> : null}
      <footer className="flex justify-end gap-3 border-t border-border pt-4"><button className={tw('action-button action-button-secondary')} type="button" onClick={onClose}>Cancel</button><button className={tw('action-button action-button-primary')} disabled={create.isPending || !data.name.trim()} type="submit"><Building2 size={18} />{create.isPending ? 'Creating...' : data.owner_mode === 'draft' ? 'Create Draft' : 'Create organization'}</button></footer>
    </form>
  </section></div>
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
