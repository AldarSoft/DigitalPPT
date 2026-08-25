import { Link, Navigate, Outlet, useLocation } from 'react-router-dom'
import { ShieldAlert } from 'lucide-react'
import { useAuth } from '../../contexts/AuthContext'
import { tw } from '../../lib/tailwind-styles'

export function RequireStaff() {
  const auth = useAuth()
  const location = useLocation()

  if (!auth.ready) {
    return <main className={tw('route-loading')}>Loading workspace...</main>
  }

  if (!auth.user) {
    return (
      <Navigate
        to="/login"
        state={{ from: `${location.pathname}${location.search}` }}
        replace
      />
    )
  }

  if (auth.user.is_staff !== true) {
    return <main className={tw('route-loading')}><section className="max-w-md rounded-panel border border-border bg-white p-6 text-center"><ShieldAlert className="mx-auto text-warning" size={28} /><h1 className="mt-3 text-xl">Admin access required</h1><p className="mt-2 text-sm text-muted">Your account does not have permission to open the administration workspace.</p><Link className="mt-5 inline-flex min-h-10 items-center rounded-control bg-brand px-4 text-sm font-bold text-white" to="/account">Return to account</Link></section></main>
  }

  return <Outlet />
}
