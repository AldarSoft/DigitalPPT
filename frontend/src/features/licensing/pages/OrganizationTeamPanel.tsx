import { useQuery } from '@tanstack/react-query'
import { ShieldCheck, UserPlus } from 'lucide-react'
import { api } from '../../../lib/api'
import { organizationTeamFixture } from '../fixtures'
import { licensingKeys } from '../queryKeys'

export function OrganizationTeamPanel() {
  const teamQuery = useQuery({ queryKey: licensingKeys.team(), queryFn: api.organizationTeam, placeholderData: organizationTeamFixture })
  const people = teamQuery.data
    ? [
        ...(teamQuery.data.owner ? [{ ...teamQuery.data.owner, rowId: `owner-${teamQuery.data.owner.id}`, kind: 'owner' as const, role: 'Organization Owner', status: 'Active' }] : []),
        ...teamQuery.data.license_managers.map((manager) => ({ ...manager, rowId: `manager-${manager.membership_id}`, kind: 'manager' as const, role: 'License Manager', status: 'Active' })),
        ...teamQuery.data.pending_invitations.map((invitation) => ({ rowId: `invitation-${invitation.invitation_id}`, kind: 'invitation' as const, name: invitation.email, email: invitation.email, role: 'License Manager', status: 'Invitation pending' })),
      ]
    : []

  return <div className="grid gap-4">
    <header className="flex flex-wrap items-start justify-between gap-4"><div><h2 className="text-[28px] leading-tight">Organization team</h2><p className="mt-1 text-sm text-muted">{teamQuery.data?.organization.name} · Owners and License Managers</p></div><button className="inline-flex min-h-11 items-center gap-2 rounded-control border-0 bg-brand px-4 text-sm font-bold text-white" type="button" disabled={!teamQuery.data?.permissions.can_invite}><UserPlus size={19} />Invite License Manager</button></header>
    {teamQuery.isError ? <p className="rounded-control bg-danger-soft px-3 py-2 text-sm text-danger">Live team data could not be loaded. Showing the approved page shell.</p> : null}
    {teamQuery.data?.owner ? <section className="rounded-panel border border-border bg-white p-5"><div className="grid items-center gap-4 md:grid-cols-[minmax(0,1fr)_auto]"><Person name={teamQuery.data.owner.name} email={teamQuery.data.owner.email} /><span className="w-fit rounded-full bg-brand-soft px-3 py-1.5 text-xs font-bold text-brand">Billing and team control</span></div></section> : null}
    <section className="rounded-panel border border-border bg-white p-5">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3"><h3 className="text-xl">License Managers</h3><span className="text-sm text-muted">{teamQuery.data?.license_managers.length ?? 0} active · {teamQuery.data?.pending_invitations.length ?? 0} invitation pending</span></div>
      <div className="hidden grid-cols-[minmax(0,1.2fr)_minmax(150px,.6fr)_minmax(130px,.5fr)_70px] gap-4 bg-surface-raised px-3 py-2.5 text-xs font-bold text-muted md:grid"><span>Name</span><span>Role</span><span>Status</span><span /></div>
      {people.filter((person) => person.kind !== 'owner').map((person) => <article className="grid gap-3 border-b border-border px-3 py-5 last:border-b-0 md:grid-cols-[minmax(0,1.2fr)_minmax(150px,.6fr)_minmax(130px,.5fr)_70px] md:items-center" key={person.rowId}><Person name={person.name} email={person.email} /><span className="text-sm">{person.role}</span><span className={`w-fit rounded-full px-3 py-1.5 text-xs font-bold ${person.status === 'Active' ? 'bg-success-soft text-success' : 'bg-warning-soft text-warning'}`}>{person.status}</span><button className="w-fit border-0 bg-transparent text-sm font-bold text-brand" type="button">{person.status === 'Active' ? 'Manage' : 'Resend'}</button></article>)}
      {people.every((person) => person.kind === 'owner') ? <div className="py-8 text-center"><strong className="block text-sm">No License Managers yet</strong><p className="mt-1 text-xs text-muted">Invite a License Manager to help manage organization licenses.</p></div> : null}
    </section>
    <p className="flex items-start gap-3 rounded-control bg-surface-muted px-4 py-3 text-sm text-muted"><ShieldCheck className="mt-0.5 shrink-0" size={19} />Only the Organization Owner can transfer organization ownership. Digital PTT support can help when the owner is unavailable.</p>
  </div>
}

function Person({ name, email }: { name: string; email: string }) {
  const initials = name.split(/\s+/).map((part) => part[0]).join('').slice(0, 2).toUpperCase()
  return <div className="flex min-w-0 items-center gap-3"><span className="inline-flex size-11 shrink-0 items-center justify-center rounded-full bg-brand-soft text-sm font-bold text-brand">{initials}</span><div className="min-w-0"><strong className="block truncate">{name}</strong><span className="block truncate text-sm text-muted">{email}</span></div></div>
}
