import { Navigate, Outlet, useLocation } from 'react-router'
import { Icon } from '../components/ui/Icon'
import { useAuth } from './context'

function FullScreenLoading() {
  return (
    <div role="status" className="flex h-screen items-center justify-center gap-3 bg-canvas text-muted">
      <Icon name="logo" size={24} className="text-accent" />
      Loading LifePilot…
    </div>
  )
}

/** Signed-in routes. Anonymous visitors go to /login and come back here afterwards. */
export function RequireAuth() {
  const { state } = useAuth()
  const location = useLocation()

  if (state.status === 'loading') return <FullScreenLoading />
  if (state.status === 'anonymous') {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />
  }
  return <Outlet />
}

/** Login and register pages. Once signed in, continue to where the user was heading. */
export function PublicOnly() {
  const { state } = useAuth()
  const location = useLocation()

  if (state.status === 'loading') return <FullScreenLoading />
  if (state.status === 'authenticated') {
    const from = (location.state as { from?: string } | null)?.from
    // Only follow in-app paths, never an absolute URL (open-redirect protection).
    const target = from && from.startsWith('/') && !from.startsWith('//') ? from : '/'
    return <Navigate to={target} replace />
  }
  return <Outlet />
}
