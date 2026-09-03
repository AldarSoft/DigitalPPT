import { Navigate, Outlet, useLocation } from 'react-router-dom'
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
    return <Navigate to="/" replace />
  }

  return <Outlet />
}

export function RequireStaffPermission({ anyOf, role }: { anyOf?: string[]; role?: string }) {
  const auth = useAuth()

  if (!auth.ready) {
    return <main className={tw('route-loading')}>Loading workspace...</main>
  }
  if (!auth.user?.is_staff) {
    return <Navigate to="/" replace />
  }

  const hasRole = !role || (auth.user.staff_roles ?? []).includes(role)
  const hasPermission =
    !anyOf?.length || anyOf.some((permission) => (auth.user!.staff_permissions ?? []).includes(permission))
  if (!hasRole || !hasPermission) {
    return <Navigate to="/admin" replace />
  }
  return <Outlet />
}
