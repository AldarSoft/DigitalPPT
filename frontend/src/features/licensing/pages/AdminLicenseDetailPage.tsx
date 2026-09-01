import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, ArrowLeft, Bell, CalendarDays, CreditCard, KeyRound, LoaderCircle, RefreshCw, Send, ShieldCheck, UserPlus, Users, X } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'
import { toast } from 'sonner'
import { Pagination } from '../../../components/Pagination'
import { ApiError, api } from '../../../lib/api'
import { tw } from '../../../lib/tailwind-styles'
import { LicenseStatusBadge } from '../components/LicenseStatusBadge'
import { licensingKeys } from '../queryKeys'
import type { AdminOrganizationUsers, ClientLicenseDetail, LicenseStatus } from '../types'

const HISTORY_PAGE_SIZE = 5

export function AdminLicenseDetailPage() {
  const organizationId = Number(useParams().organizationId)
  const queryClient = useQueryClient()
  const [adjustingLicense, setAdjustingLicense] = useState<ClientLicenseDetail | null>(null)
  const [notificationOpen, setNotificationOpen] = useState(false)
  const [renewalInvoiceOpen, setRenewalInvoiceOpen] = useState(false)
  const [organizationUsersOpen, setOrganizationUsersOpen] = useState(false)
  const [historyPage, setHistoryPage] = useState(1)
  const detailQuery = useQuery({
    queryKey: licensingKeys.adminOrganization(organizationId),
    queryFn: () => api.adminLicenseOrganization(organizationId),
    enabled: Number.isInteger(organizationId) && organizationId > 0,
  })
  const historyQuery = useQuery({
    queryKey: licensingKeys.adminHistory(organizationId, historyPage),
    queryFn: () => api.adminLicenseHistory(organizationId, historyPage, HISTORY_PAGE_SIZE),
    enabled: Number.isInteger(organizationId) && organizationId > 0,
  })
  const organizationUsersQuery = useQuery({
    queryKey: [...licensingKeys.adminOrganization(organizationId), 'users'],
    queryFn: () => api.adminOrganizationUsers(organizationId),
    enabled: organizationUsersOpen && Number.isInteger(organizationId) && organizationId > 0,
    retry: false,
  })
  const renewalInvoiceMutation = useMutation({
    mutationFn: () => api.sendAdminRenewalInvoice(organizationId),
    onSuccess: () => void refreshDetail(),
  })
  const refreshDetail = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: licensingKeys.adminOrganization(organizationId) }),
      queryClient.invalidateQueries({ queryKey: [...licensingKeys.adminOrganization(organizationId), 'history'] }),
    ])
  }
  const detail = detailQuery.data
  const accessDenied = detailQuery.error instanceof ApiError && [401, 403].includes(detailQuery.error.status)
  const invalidOrganization = !Number.isInteger(organizationId) || organizationId < 1

  if (invalidOrganization) return <main className={tw('admin-page')}><AdminDetailState icon={<AlertTriangle className="text-danger" size={22} />} title="Invalid organization link" text="Return to License Management and open an organization from the list." /></main>

  return (
    <main className={tw('admin-page')}>
      <Link className="mb-4 inline-flex items-center gap-2 font-bold text-primary hover:underline" to="/admin/licenses"><ArrowLeft size={18} />Back to license management</Link>
      <div className={tw('admin-title-row')}>
        <div><p className={tw('admin-breadcrumb')}>Workspace / License management / Organization</p><h1>{detail?.organization.name ?? 'Organization license details'}</h1><p>Organization license details · {detail?.organization.owner?.name ?? 'No owner'} is the Organization Owner</p></div>
        {detail ? <LicenseStatusBadge status={detail.summary.status} /> : null}
      </div>
      {detailQuery.isLoading ? <AdminDetailState icon={<LoaderCircle className="animate-spin text-brand" size={22} />} title="Loading organization licenses" text="Retrieving subscription, license capacity, and support history." /> : null}
      {accessDenied ? <AdminDetailState icon={<ShieldCheck className="text-warning" size={22} />} title="Organization license access is required" text="Only Digital PTT administrators can open this organization." /> : null}
      {detailQuery.isError && !accessDenied ? <AdminDetailState icon={<AlertTriangle className="text-danger" size={22} />} title="Organization details could not be loaded" text={messageFrom(detailQuery.error)} action={<button className="min-h-9 rounded-control border border-border-input bg-white px-3 text-xs font-bold text-brand" type="button" onClick={() => void detailQuery.refetch()}>Try again</button>} /> : null}
      {detail?.summary.overflow_quantity ? <section className="mb-4 flex items-start gap-3 rounded-panel border border-danger bg-danger-soft px-5 py-4 text-danger"><AlertTriangle className="mt-0.5 shrink-0" size={21} /><div><h2 className="text-base">License capacity warning</h2><p className="mt-1 text-sm">{detail.summary.overflow_quantity} purchased radio product(s) are beyond usable compatible capacity. The organization and staff receive one in-app reminder per day until coverage is restored.</p></div></section> : null}
      {detail ? (
        <div className="grid gap-4">
          <section className="grid gap-3 md:grid-cols-3">
            <SummaryCard icon={CalendarDays} label="Subscription" value={`${formatDate(detail.summary.subscription_starts_on)} – ${formatDate(detail.summary.subscription_expires_on)}`} note="Annual subscription" />
            <SummaryCard icon={Users} label="Organization control" value={`${detail.organization.owner ? 1 : 0} Owner · ${detail.organization.license_manager_count} License Managers`} note={detail.organization.owner ? `${detail.organization.owner.name} · ${detail.organization.owner.email}` : 'No owner'} action="Manage users" onAction={() => setOrganizationUsersOpen(true)} />
            <SummaryCard icon={CreditCard} label="Licensed products" value={`${detail.summary.licensed_product_count} products · ${detail.summary.active_quantity} radios`} note={`${detail.summary.usable_license_capacity} usable capacity`} />
          </section>
          <div className="grid items-start gap-4 xl:grid-cols-[minmax(0,1.45fr)_minmax(280px,.7fr)]">
            <section className={tw('admin-panel admin-table-wrap')}>
              <div className="flex items-center justify-between gap-3 px-4 py-3"><div><h2 className="text-xl">Product licenses</h2><p className="mt-1 text-xs text-muted">Capacity, assigned products, and expiry by license.</p></div><span className="text-xs text-muted">Changes are audited</span></div>
              {detail.licenses.length ? <table className={tw('admin-table admin-table-compact')}><thead><tr><th>License</th><th>Capacity</th><th>Assigned</th><th>Expiry</th><th>Action</th></tr></thead><tbody>{detail.licenses.map((license) => <tr key={license.license_number}><td><strong className="block">{license.name}</strong><span className="text-[11px] text-muted">{license.license_number}</span></td><td>{license.capacity}</td><td>{license.used_capacity}</td><td><div className="inline-flex items-center gap-2 whitespace-nowrap"><span>{formatDate(license.expires_on)}</span><LicenseStatusBadge status={license.status} /></div></td><td><button className="border-0 bg-transparent text-xs font-bold text-brand" type="button" onClick={() => setAdjustingLicense(license)}>Adjust</button></td></tr>)}</tbody></table> : <p className="px-4 py-8 text-center text-sm text-muted">No product licenses have been created for this organization.</p>}
            </section>
            <aside className={tw('admin-panel')}>
              <h2 className="text-xl">Support and notifications</h2>
              <Action icon={Bell} title="Renewal reminder" note={detail.notifications.renewal_reminder_scheduled_for ? `Scheduled for ${formatDate(detail.notifications.renewal_reminder_scheduled_for)}` : 'Not scheduled'} action="Compose" onClick={() => setNotificationOpen(true)} />
              <Action icon={CreditCard} title="Renewal request" note={detail.notifications.renewal_invoice_status === 'issued' ? 'Client notified' : 'Not sent'} action={renewalInvoiceMutation.isPending ? 'Sending...' : detail.notifications.renewal_invoice_status === 'issued' ? 'Send again' : 'Send request'} disabled={renewalInvoiceMutation.isPending} onClick={() => setRenewalInvoiceOpen(true)} />
            </aside>
          </div>
          <section className={tw('admin-panel')} id="license-history">
            <div className="flex items-center justify-between gap-3">
              <div>
                <h2 className="text-xl">License history</h2>
                <p className="mt-1 text-sm text-muted">Provisioning, renewal, notification, and adjustment activity.</p>
              </div>
              {historyQuery.isFetching ? <LoaderCircle className="animate-spin text-brand" size={19} /> : null}
            </div>
            {historyQuery.isError ? <p className="mt-3 rounded-control bg-danger-soft px-3 py-2 text-sm text-danger">Could not load license history.</p> : null}
            <ol className="mt-3 grid gap-0">
              {historyQuery.data?.results.map((event) => (
                <li className="grid gap-2 border-t border-border py-4 first:border-t-0 md:grid-cols-[150px_14px_minmax(0,1fr)] md:gap-4" key={event.id}>
                  <time className="text-xs font-bold text-muted">{formatDateTime(event.created_at)}</time>
                  <span className="mt-1 hidden size-2 rounded-full bg-brand md:block" />
                  <div>
                    <strong className="block text-sm">{event.message}</strong>
                    <span className="text-xs text-muted">{event.actor_name}{event.license_number ? ` · ${event.license_number}` : ''}</span>
                  </div>
                </li>
              ))}
            </ol>
            {!historyQuery.isLoading && !historyQuery.data?.results.length ? <p className="mt-3 text-sm text-muted">No license events have been recorded yet.</p> : null}
            <Pagination
              page={historyPage}
              pageSize={HISTORY_PAGE_SIZE}
              total={historyQuery.data?.count ?? 0}
              loading={historyQuery.isFetching}
              className="mt-4 border-t border-border pt-4"
              onPageChange={setHistoryPage}
            />
          </section>
        </div>
      ) : null}
      {adjustingLicense ? <AdjustmentDialog organizationId={organizationId} license={adjustingLicense} onClose={() => setAdjustingLicense(null)} onSaved={() => { setAdjustingLicense(null); void refreshDetail() }} /> : null}
      {notificationOpen && detail ? <NotificationDialog organizationId={organizationId} licenses={detail.licenses} onClose={() => setNotificationOpen(false)} onSent={() => { setNotificationOpen(false); void refreshDetail() }} /> : null}
      {renewalInvoiceOpen && detail ? <RenewalRequestDialog organizationName={detail.organization.name} pending={renewalInvoiceMutation.isPending} error={renewalInvoiceMutation.error} onClose={() => setRenewalInvoiceOpen(false)} onConfirm={() => renewalInvoiceMutation.mutate(undefined, { onSuccess: () => { setRenewalInvoiceOpen(false); void refreshDetail() } })} /> : null}
      {organizationUsersOpen ? <OrganizationUsersDialog organizationId={organizationId} data={organizationUsersQuery.data} loading={organizationUsersQuery.isLoading} error={organizationUsersQuery.error} onClose={() => setOrganizationUsersOpen(false)} onRetry={() => void organizationUsersQuery.refetch()} onChanged={() => { void organizationUsersQuery.refetch(); void refreshDetail() }} /> : null}
    </main>
  )
}

function SummaryCard({ icon: Icon, label, value, note, action, onAction }: { icon: typeof CalendarDays; label: string; value: string; note: string; action?: string; onAction?: () => void }) {
  return <article className={tw('admin-panel')}><div className="flex items-center justify-between gap-3"><span className="text-xs font-bold text-muted">{label}</span><Icon className="text-brand" size={19} /></div><strong className="mt-3 block text-base">{value}</strong><span className="mt-2 block text-xs capitalize text-muted">{note}</span>{action && onAction ? <button className="mt-3 border-0 bg-transparent p-0 text-xs font-bold text-brand" type="button" onClick={onAction}>{action}</button> : null}</article>
}

function Action({ icon: Icon, title, note, action, onClick, disabled = false }: { icon: typeof Bell; title: string; note: string; action: string; onClick: () => void; disabled?: boolean }) {
  return <div className="grid grid-cols-[24px_minmax(0,1fr)_auto] gap-3 border-b border-border py-4 last:border-b-0"><Icon className="mt-0.5 text-muted" size={20} /><div><strong className="block text-sm">{title}</strong><span className="mt-1 block text-xs capitalize text-muted">{note}</span></div><button className="border-0 bg-transparent text-xs font-bold text-brand disabled:opacity-55" type="button" disabled={disabled} onClick={onClick}>{action}</button></div>
}

function formatDate(value: string | null) {
  return value ? new Intl.DateTimeFormat('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }).format(new Date(value)) : 'Not set'
}

function formatDateTime(value: string) {
  return new Intl.DateTimeFormat('en-GB', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' }).format(new Date(value))
}

function AdjustmentDialog({ organizationId, license, onClose, onSaved }: { organizationId: number; license: ClientLicenseDetail; onClose: () => void; onSaved: () => void }) {
  const [capacity, setCapacity] = useState(String(license.capacity))
  const [status, setStatus] = useState<LicenseStatus>(license.status)
  const [reason, setReason] = useState('')
  const mutation = useMutation({ mutationFn: () => api.adjustAdminLicense(organizationId, license.license_number, { capacity: Number(capacity), status, reason }), onSuccess: onSaved })
  return <Dialog title={`Adjust ${license.name}`} onClose={onClose}><form className="grid gap-3" onSubmit={(event) => { event.preventDefault(); mutation.mutate() }}><label className="grid gap-1.5 text-sm font-bold">Capacity<input className="min-h-11 rounded-control border border-border-input px-3 font-normal" type="number" min={license.used_capacity} value={capacity} onChange={(event) => setCapacity(event.target.value)} required /></label><label className="grid gap-1.5 text-sm font-bold">Status<select className="min-h-11 rounded-control border border-border-input bg-white px-3 font-normal" value={status} onChange={(event) => setStatus(event.target.value as LicenseStatus)}>{(['active', 'expiring_soon', 'expired', 'cancelled', 'pending_payment'] as LicenseStatus[]).map((value) => <option value={value} key={value}>{value.replaceAll('_', ' ')}</option>)}</select></label><label className="grid gap-1.5 text-sm font-bold">Reason<textarea className="min-h-24 rounded-control border border-border-input p-3 font-normal" value={reason} onChange={(event) => setReason(event.target.value)} required /></label>{mutation.isError ? <p className="rounded-control bg-danger-soft px-3 py-2 text-sm text-danger">{messageFrom(mutation.error)}</p> : null}<SubmitButton pending={mutation.isPending} label="Save adjustment" /></form></Dialog>
}

function NotificationDialog({ organizationId, licenses, onClose, onSent }: { organizationId: number; licenses: ClientLicenseDetail[]; onClose: () => void; onSent: () => void }) {
  const [licenseNumber, setLicenseNumber] = useState('')
  const [title, setTitle] = useState('License renewal reminder')
  const [message, setMessage] = useState('Your organization license is approaching its renewal date. Please contact Digital PTT support for renewal assistance.')
  const mutation = useMutation({ mutationFn: () => api.sendAdminLicenseNotification(organizationId, { title, message, license_number: licenseNumber || undefined }), onSuccess: onSent })
  return <Dialog title="Send license notification" onClose={onClose}><form className="grid gap-3" onSubmit={(event) => { event.preventDefault(); mutation.mutate() }}><label className="grid gap-1.5 text-sm font-bold">License (optional)<select className="min-h-11 rounded-control border border-border-input bg-white px-3 font-normal" value={licenseNumber} onChange={(event) => setLicenseNumber(event.target.value)}><option value="">All organization licenses</option>{licenses.map((license) => <option value={license.license_number} key={license.license_number}>{license.name} · {license.license_number}</option>)}</select></label><label className="grid gap-1.5 text-sm font-bold">Title<input className="min-h-11 rounded-control border border-border-input px-3 font-normal" value={title} onChange={(event) => setTitle(event.target.value)} required /></label><label className="grid gap-1.5 text-sm font-bold">Message<textarea className="min-h-28 rounded-control border border-border-input p-3 font-normal" value={message} onChange={(event) => setMessage(event.target.value)} required /></label>{mutation.isError ? <p className="rounded-control bg-danger-soft px-3 py-2 text-sm text-danger">{messageFrom(mutation.error)}</p> : null}<SubmitButton pending={mutation.isPending} label="Send notification" icon={<Send size={17} />} /></form></Dialog>
}

function RenewalRequestDialog({ organizationName, pending, error, onClose, onConfirm }: { organizationName: string; pending: boolean; error: unknown; onClose: () => void; onConfirm: () => void }) {
  return <Dialog title="Send renewal request" onClose={pending ? () => undefined : onClose}><div className="grid gap-4"><div className="rounded-control border border-[#f1d29a] bg-warning-soft px-3 py-3 text-sm text-warning"><strong className="block">This does not create an invoice or payment.</strong><p className="mt-1">It sends a renewal-review notification to {organizationName}&apos;s active Owner and License Managers, and displays the request on their Organization licenses page.</p></div><p className="text-sm text-muted">Use this when Digital PTT is ready to begin the renewal conversation. Licenses are not extended until a renewal purchase is completed and paid.</p>{error ? <p className="rounded-control bg-danger-soft px-3 py-2 text-sm text-danger">{messageFrom(error)}</p> : null}<div className="flex justify-end gap-3"><button className="min-h-10 rounded-control border border-border-input bg-white px-4 text-sm font-bold" type="button" disabled={pending} onClick={onClose}>Cancel</button><button className="min-h-10 rounded-control border-0 bg-brand px-4 text-sm font-bold text-white disabled:opacity-55" type="button" disabled={pending} onClick={onConfirm}>{pending ? 'Sending request...' : 'Send renewal request'}</button></div></div></Dialog>
}

function OrganizationUsersDialog({ organizationId, data, loading, error, onClose, onRetry, onChanged }: { organizationId: number; data: AdminOrganizationUsers | undefined; loading: boolean; error: unknown; onClose: () => void; onRetry: () => void; onChanged: () => void }) {
  const [email, setEmail] = useState('')
  const [ownerCandidate, setOwnerCandidate] = useState<AdminOrganizationUsers['license_managers'][number] | null>(null)
  const assigningInitialOwner = Boolean(data && !data.owner)
  const invite = useMutation({ mutationFn: () => api.inviteAdminOrganizationLicenseManager(organizationId, email), onSuccess: () => { setEmail(''); onChanged() } })
  const transfer = useMutation({ mutationFn: (membershipId: number) => api.transferAdminOrganizationOwnership(organizationId, membershipId), onSuccess: () => { setOwnerCandidate(null); onChanged() } })
  const resend = useMutation({ mutationFn: (invitationId: number) => api.resendAdminOrganizationInvitation(organizationId, invitationId), onSuccess: onChanged })
  const revoke = useMutation({ mutationFn: (invitationId: number) => api.revokeAdminOrganizationInvitation(organizationId, invitationId), onSuccess: onChanged })
  const resetPassword = useMutation({ mutationFn: (userEmail: string) => api.resetPassword(userEmail), onSuccess: () => toast.success('Password reset email sent.') })
  const mutationError = invite.error ?? transfer.error ?? resend.error ?? revoke.error ?? resetPassword.error

  return <><Dialog title={data ? `${data.organization.name} users` : 'Organization users'} onClose={onClose}>
    {loading ? <div className="flex min-h-48 items-center justify-center text-sm text-muted"><LoaderCircle className="mr-2 animate-spin text-brand" size={19} />Loading organization users...</div> : null}
    {error ? <div className="grid min-h-48 place-items-center text-center"><div><strong>Users could not be loaded</strong><p className="mt-1 text-sm text-muted">{messageFrom(error)}</p><button className="mt-3 min-h-9 rounded-control border border-border-input bg-white px-3 text-xs font-bold text-brand" type="button" onClick={onRetry}>Try again</button></div></div> : null}
    {data ? <div className="grid gap-5">
      <section><div className="mb-2 flex items-center justify-between gap-3"><h3 className="text-sm">Organization Owner</h3><span className="text-xs text-muted">Full organization control</span></div>{data.owner ? <UserRow member={data.owner} resetPending={resetPassword.isPending} onReset={() => resetPassword.mutate(data.owner!.email)} /> : <p className="rounded-control bg-warning-soft px-3 py-2 text-sm text-warning">No active owner is assigned.</p>}</section>
      <section><h3 className="text-sm">License Managers</h3><div className="mt-2 divide-y divide-border rounded-panel border border-border">{data.license_managers.length ? data.license_managers.map((member) => <div className="flex flex-wrap items-center justify-between gap-3 px-3 py-3" key={member.membership_id}><div className="min-w-0"><strong className="block truncate text-sm">{member.name}</strong><span className="block truncate text-xs text-muted">{member.email} · License Manager</span></div><div className="grid min-w-28 gap-2"><button className="min-h-9 rounded-control border border-danger bg-danger-soft px-3 text-xs font-bold text-danger disabled:opacity-55" type="button" disabled={transfer.isPending} onClick={() => setOwnerCandidate(member)}>{assigningInitialOwner ? 'Assign owner' : 'Make owner'}</button><button className="inline-flex min-h-9 items-center justify-center gap-1 rounded-control border border-border-input bg-white px-3 text-xs font-bold text-brand disabled:opacity-55" type="button" disabled={resetPassword.isPending} onClick={() => resetPassword.mutate(member.email)}><KeyRound size={14} />Send reset</button></div></div>) : <p className="px-3 py-4 text-sm text-muted">No License Managers yet.</p>}</div></section>
      <section className="border-t border-border pt-4"><h3 className="text-sm">Invite License Manager</h3><form className="mt-2 flex flex-wrap gap-2" onSubmit={(event) => { event.preventDefault(); invite.mutate() }}><input className="min-h-10 min-w-0 flex-1 rounded-control border border-border-input px-3 text-sm" type="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="name@company.com" required /><button className="inline-flex min-h-10 items-center gap-2 rounded-control border-0 bg-brand px-3 text-sm font-bold text-white disabled:opacity-55" type="submit" disabled={invite.isPending}><UserPlus size={16} />Invite</button></form></section>
      {data.pending_invitations.length ? <section><h3 className="text-sm">Pending invitations</h3><div className="mt-2 divide-y divide-border rounded-panel border border-border">{data.pending_invitations.map((item) => <div className="flex flex-wrap items-center justify-between gap-3 px-3 py-3" key={item.invitation_id}><div className="min-w-0"><strong className="block truncate text-sm">{item.email}</strong><span className="text-xs text-warning">Invitation pending</span></div><div className="flex gap-2"><button className="inline-flex min-h-9 items-center gap-1 rounded-control border border-border-input bg-white px-2.5 text-xs font-bold text-brand disabled:opacity-55" type="button" disabled={resend.isPending} onClick={() => resend.mutate(item.invitation_id)}><RefreshCw size={14} />Resend</button><button className="min-h-9 rounded-control border border-danger bg-white px-2.5 text-xs font-bold text-danger disabled:opacity-55" type="button" disabled={revoke.isPending} onClick={() => revoke.mutate(item.invitation_id)}>Revoke</button></div></div>)}</div></section> : null}
      {mutationError ? <p className="rounded-control bg-danger-soft px-3 py-2 text-sm text-danger">{messageFrom(mutationError)}</p> : null}
    </div> : null}
  </Dialog>{ownerCandidate ? <Dialog title={assigningInitialOwner ? 'Confirm owner assignment' : 'Confirm ownership transfer'} onClose={transfer.isPending ? () => undefined : () => setOwnerCandidate(null)}><div className="grid gap-4"><div className="flex items-start gap-3 rounded-control border border-danger bg-danger-soft px-3 py-3 text-danger"><AlertTriangle className="mt-0.5 shrink-0" size={20} /><div><strong className="block text-sm">{assigningInitialOwner ? `Assign ${ownerCandidate.name} as the Organization Owner?` : `Make ${ownerCandidate.name} the Organization Owner?`}</strong><p className="mt-1 text-sm">{assigningInitialOwner ? 'This activates the draft organization. The new Owner will receive full organization, billing, and team control.' : 'The current Owner will become a License Manager. The new Owner will receive full organization, billing, and team control.'}</p></div></div>{transfer.error ? <p className="rounded-control bg-danger-soft px-3 py-2 text-sm text-danger">{messageFrom(transfer.error)}</p> : null}<div className="flex justify-end gap-3"><button className="min-h-10 rounded-control border border-border-input bg-white px-4 text-sm font-bold" type="button" disabled={transfer.isPending} onClick={() => setOwnerCandidate(null)}>Cancel</button><button className="min-h-10 rounded-control border-0 bg-danger px-4 text-sm font-bold text-white disabled:opacity-55" type="button" disabled={transfer.isPending} onClick={() => transfer.mutate(ownerCandidate.membership_id)}>{transfer.isPending ? (assigningInitialOwner ? 'Assigning...' : 'Transferring...') : (assigningInitialOwner ? 'Assign owner' : 'Confirm transfer')}</button></div></div></Dialog> : null}</>
}

function UserRow({ member, onReset, resetPending }: { member: { name: string; email: string; role: string }; onReset: () => void; resetPending: boolean }) {
  return <div className="flex flex-wrap items-center justify-between gap-3 rounded-panel border border-border px-3 py-3"><div className="min-w-0"><strong className="block truncate text-sm">{member.name}</strong><span className="block truncate text-xs text-muted">{member.email} · {member.role === 'owner' ? 'Organization Owner' : 'License Manager'}</span></div><button className="inline-flex min-h-9 items-center gap-1 rounded-control border border-border-input bg-white px-2.5 text-xs font-bold text-brand disabled:opacity-55" type="button" disabled={resetPending} onClick={onReset}><KeyRound size={14} />Send reset</button></div>
}

function Dialog({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) {
  return <div className="fixed inset-0 z-50 grid place-items-center bg-[#09172d]/45 p-4" role="presentation" onMouseDown={onClose}><section aria-modal="true" className="w-full max-w-lg rounded-panel border border-border bg-white p-5 shadow-xl" role="dialog" onMouseDown={(event) => event.stopPropagation()}><div className="mb-4 flex items-start justify-between gap-3"><h2 className="text-xl">{title}</h2><button aria-label="Close dialog" className="inline-flex size-9 items-center justify-center rounded-control border-0 bg-surface-muted" type="button" onClick={onClose}><X size={19} /></button></div>{children}</section></div>
}

function SubmitButton({ pending, label, icon }: { pending: boolean; label: string; icon?: React.ReactNode }) {
  return <div className="mt-1 flex justify-end"><button className="inline-flex min-h-10 items-center justify-center gap-2 rounded-control border-0 bg-brand px-4 text-sm font-bold text-white disabled:opacity-55" type="submit" disabled={pending}>{pending ? 'Saving...' : <>{icon}{label}</>}</button></div>
}

function messageFrom(error: unknown) {
  return error instanceof ApiError || error instanceof Error ? error.message : 'Please try again.'
}

function AdminDetailState({ icon, title, text, action }: { icon: React.ReactNode; title: string; text: string; action?: React.ReactNode }) {
  return <section className="mt-4 flex items-start gap-3 rounded-panel border border-border bg-white px-5 py-4"><span className="mt-0.5 shrink-0">{icon}</span><div><h2 className="text-base">{title}</h2><p className="mt-1 text-sm text-muted">{text}</p>{action ? <div className="mt-3">{action}</div> : null}</div></section>
}
