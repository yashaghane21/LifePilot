import { useEffect, useState } from 'react'

export type ApiState<T> =
  | { status: 'loading' }
  | { status: 'error'; error: Error }
  | { status: 'success'; data: T }

/**
 * Loads data once per `load` function and tracks loading / error / success.
 * `load` must be a stable reference (e.g. `api.getDashboard`), or it reloads every render.
 * Replaced by TanStack Query once real API calls need caching and refetching.
 */
export function useApi<T>(load: () => Promise<T>): ApiState<T> {
  const [state, setState] = useState<ApiState<T>>({ status: 'loading' })

  useEffect(() => {
    // Ignore a response that arrives after the component unmounted or `load` changed.
    let cancelled = false
    load().then(
      (data) => {
        if (!cancelled) setState({ status: 'success', data })
      },
      (error: unknown) => {
        if (!cancelled) {
          setState({ status: 'error', error: error instanceof Error ? error : new Error(String(error)) })
        }
      },
    )
    return () => {
      cancelled = true
    }
  }, [load])

  return state
}
