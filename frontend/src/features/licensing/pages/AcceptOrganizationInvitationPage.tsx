import { useState } from 'react'
import { CheckCircle2, KeyRound, ShieldCheck } from 'lucide-react'
import { Link, Navigate, useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { useAuth } from '../../../contexts/AuthContext'
import { ApiError, api } from '../../../lib/api'

export function AcceptOrganizationInvitationPage() {
  const auth = useAuth()
  const location = useLocation()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const token = searchParams.get('token')?.trim() ?? ''
  const returnPath = `${location.pathname}${location.search}`

  if (!token) return <InvitationState title="Invitation link is incomplete" text="Use the complete invitation link from your email, or ask the Organization Owner to resend it." />
  if (!auth.ready) return <InvitationState title="Loading invitation" text="Checking your account session." />
  if (!auth.user) return <Navigate to="/login" state={{ from: returnPath }} replace />

  const accept = async () => {
    setSubmitting(true)
    setError(null)
    try {
      const result = await api.acceptOrganizationInvitation(token)
      navigate(`/account?tab=team&org=${result.organization_id}`, { replace: true, state: { invitedOrganization: result.organization_name } })
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.message : 'The invitation could not be accepted.')
    } finally {
      setSubmitting(false)
    }
  }

  return <main className="flex min-h-[70vh] items-center justify-center bg-surface px-5 py-10"><section className="w-full max-w-lg rounded-panel border border-border bg-white p-6"><span className="inline-flex size-11 items-center justify-center rounded-control bg-brand-soft text-brand"><KeyRound size={22} /></span><p className="mt-5 text-xs font-bold tracking-[.12em] text-brand">ORGANIZATION INVITATION</p><h1 className="mt-2 text-2xl">Join as a License Manager</h1><p className="mt-3 text-sm text-muted">You are signed in as <strong className="text-ink">{auth.user.email}</strong>. Accepting gives this account access to the organization&apos;s licenses, capacity, and renewal information.</p>{error ? <p className="mt-4 rounded-control bg-danger-soft px-3 py-2.5 text-sm text-danger">{error}</p> : null}<div className="mt-6 flex flex-wrap gap-3"><button className="inline-flex min-h-11 items-center gap-2 rounded-control border-0 bg-brand px-4 text-sm font-bold text-white disabled:opacity-55" type="button" disabled={submitting} onClick={accept}>{submitting ? 'Accepting invitation...' : <><CheckCircle2 size={18} />Accept invitation</>}</button><Link className="inline-flex min-h-11 items-center rounded-control border border-border-input px-4 text-sm font-bold text-ink" to="/">Cancel</Link></div><p className="mt-5 flex items-start gap-2 text-xs text-muted"><ShieldCheck className="shrink-0 text-brand" size={16} />The signed-in email must match the email that received this invitation.</p></section></main>
}

function InvitationState({ title, text }: { title: string; text: string }) {
  return <main className="flex min-h-[70vh] items-center justify-center bg-surface px-5 py-10"><section className="w-full max-w-lg rounded-panel border border-border bg-white p-6 text-center"><h1 className="text-2xl">{title}</h1><p className="mt-3 text-sm text-muted">{text}</p><Link className="mt-5 inline-flex min-h-11 items-center rounded-control bg-brand px-4 text-sm font-bold text-white" to="/">Return home</Link></section></main>
}
