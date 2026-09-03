import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, Building2, LoaderCircle, Save, ShieldCheck, Trash2 } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { api } from '../../../lib/api'
import { licensingKeys } from '../queryKeys'

export function OrganizationSettingsPanel({ organizationId, canEdit }: { organizationId: number | null; canEdit: boolean }) {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [confirmingDelete, setConfirmingDelete] = useState(false)
  const settings = useQuery({
    queryKey: licensingKeys.settings(organizationId),
    queryFn: () => api.organizationSettings(organizationId),
    enabled: Boolean(organizationId),
  })
  const update = useMutation({
    mutationFn: ({ name, billingEmail }: { name: string; billingEmail: string }) => api.updateOrganizationSettings({ name, billing_email: billingEmail }, organizationId),
    onSuccess: (organization) => {
      queryClient.setQueryData(licensingKeys.settings(organizationId), organization)
      queryClient.invalidateQueries({ queryKey: licensingKeys.workspaces() })
      toast.success('Organization settings updated')
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : 'Could not update the organization'),
  })
  const remove = useMutation({
    mutationFn: () => api.deleteOrganization(organizationId!),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: licensingKeys.workspaces() })
      toast.success('Organization deleted')
      navigate('/account?tab=licenses', { replace: true })
    },
    onError: (error) => {
      setConfirmingDelete(false)
      toast.error(error instanceof Error ? error.message : 'Could not delete the organization')
    },
  })

  if (!organizationId) return <State icon={<Building2 size={22} />} title="No organization selected" text="Select an organization workspace to view its settings." />
  if (settings.isLoading) return <State icon={<LoaderCircle className="animate-spin text-brand" size={22} />} title="Loading organization" text="Retrieving organization settings." />
  if (settings.isError || !settings.data) return <State icon={<AlertTriangle className="text-danger" size={22} />} title="Organization settings could not be loaded" text={settings.error instanceof Error ? settings.error.message : 'Please try again.'} />

  return <section className="grid gap-4">
    <header><h2 className="text-[28px] leading-tight">Organization settings</h2><p className="mt-1 text-sm text-muted">Manage the organization identity used for licensing, orders, and billing.</p></header>
    {!canEdit ? <div className="flex items-start gap-3 rounded-panel border border-border bg-white px-4 py-3 text-sm text-muted"><ShieldCheck className="mt-0.5 shrink-0 text-brand" size={19} /><span>Only the Organization Owner can edit these settings.</span></div> : null}
    <form className="grid gap-5 rounded-panel border border-border bg-white p-5" key={settings.data.id} onSubmit={(event) => { event.preventDefault(); const data = new FormData(event.currentTarget); if (canEdit) update.mutate({ name: String(data.get('name') ?? '').trim(), billingEmail: String(data.get('billing_email') ?? '').trim() }) }}>
      <label className="grid gap-2 text-sm font-bold">Organization name<input className="min-h-12 rounded-control border border-border-input px-3.5 outline-none focus:border-brand" name="name" required defaultValue={settings.data.name} disabled={!canEdit || update.isPending} /></label>
      <label className="grid gap-2 text-sm font-bold">Billing email<input className="min-h-12 rounded-control border border-border-input px-3.5 outline-none focus:border-brand" name="billing_email" type="email" placeholder={canEdit ? '' : 'Visible to the Owner only'} defaultValue={settings.data.billing_email} disabled={!canEdit || update.isPending} /></label>
      {canEdit ? <div><button className="inline-flex min-h-11 items-center gap-2 rounded-control border-0 bg-brand px-4 font-bold text-white disabled:opacity-55" disabled={update.isPending} type="submit"><Save size={18} />{update.isPending ? 'Saving...' : 'Save organization'}</button></div> : null}
    </form>
    {canEdit ? <section className="rounded-panel border border-danger bg-white p-5">
      <h3 className="flex items-center gap-2 text-lg"><Trash2 size={19} className="text-danger" />Delete organization</h3>
      <p className="mt-1 text-sm text-muted">Deleting is only possible while the organization has no licenses, orders, history, or other members. Once deleted it cannot be restored.</p>
      {!confirmingDelete ? <button className="mt-4 inline-flex min-h-10 items-center gap-2 rounded-control border border-danger bg-white px-4 text-sm font-bold text-danger hover:bg-danger-soft" type="button" onClick={() => setConfirmingDelete(true)}>Delete organization</button> : <div className="mt-4 flex flex-wrap items-center gap-3 rounded-control bg-danger-soft p-3"><AlertTriangle size={19} className="text-danger" /><span className="flex-1 text-sm font-semibold text-danger">Delete this organization permanently?</span><button className="min-h-9 rounded-control border border-border bg-white px-3 text-xs font-bold" type="button" disabled={remove.isPending} onClick={() => setConfirmingDelete(false)}>Keep organization</button><button className="min-h-9 rounded-control border-0 bg-danger px-3 text-xs font-bold text-white disabled:opacity-55" type="button" disabled={remove.isPending} onClick={() => remove.mutate()}>{remove.isPending ? 'Deleting...' : 'Delete organization'}</button></div>}
    </section> : null}
  </section>
}

function State({ icon, title, text }: { icon: React.ReactNode; title: string; text: string }) {
  return <section className="flex min-h-56 items-center justify-center rounded-panel border border-border bg-white p-6 text-center"><div>{icon}<h2 className="mt-3 text-lg">{title}</h2><p className="mt-1 text-sm text-muted">{text}</p></div></section>
}
