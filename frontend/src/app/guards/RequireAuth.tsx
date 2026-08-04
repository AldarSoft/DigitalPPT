import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from '../../contexts/AuthContext'
import { tw } from '../../lib/tailwind-styles'

export function RequireAuth() {
  const auth = useAuth()
  const location = useLocation()

  if (!auth.ready) {
    return <main className={tw('route-loading')}>Loading account...</main>
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

  return <Outlet />
}
