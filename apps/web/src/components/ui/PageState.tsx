import type { ReactNode } from 'react'
import type { ApiState } from '../../lib/useApi'

interface PageStateProps<T> {
  state: ApiState<T>
  children: (data: T) => ReactNode
}

/** Renders loading and error states for a page, and the page itself once data has arrived. */
export function PageState<T>({ state, children }: PageStateProps<T>) {
  if (state.status === 'loading') {
    return (
      <p role="status" className="p-10 text-muted">
        Loading…
      </p>
    )
  }
  if (state.status === 'error') {
    return (
      <div role="alert" className="m-10 rounded-2xl border border-warning-line bg-warning-soft p-6 text-warning">
        <p className="m-0 font-semibold">Something went wrong loading this page.</p>
        <p className="m-0 mt-1 text-sm">{state.error.message}</p>
      </div>
    )
  }
  return <>{children(state.data)}</>
}
