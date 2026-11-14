// Every real API call goes through apiFetch: it attaches the access token, refreshes it once
// on a 401, and turns error responses into ApiError.
import type { ApiErrorBody, TokenResponse } from './types'

const API_BASE = '/api/v1'

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly requestId: string | null
  readonly details: NonNullable<ApiErrorBody['details']>

  constructor(status: number, body: ApiErrorBody) {
    super(body.message)
    this.name = 'ApiError'
    this.status = status
    this.code = body.code
    this.requestId = body.request_id
    this.details = body.details ?? []
  }

  /** Validation messages keyed by field name, e.g. { password: "String should have…" }. */
  fieldErrors(): Record<string, string> {
    const fields: Record<string, string> = {}
    for (const detail of this.details) {
      const field = detail.loc.at(-1)
      if (typeof field === 'string' && !(field in fields)) fields[field] = detail.message
    }
    return fields
  }
}

async function toApiError(response: Response): Promise<ApiError> {
  try {
    const body: unknown = await response.json()
    const error = (body as { error?: ApiErrorBody }).error
    if (error && typeof error.code === 'string') return new ApiError(response.status, error)
  } catch {
    // Not our JSON error shape (e.g. a proxy error page); fall through.
  }
  return new ApiError(response.status, {
    code: 'http_error',
    message: response.status >= 500 ? 'The server had a problem. Please try again.' : `Request failed (${response.status})`,
    request_id: null,
  })
}

// The access token lives only in memory: never in localStorage, where any injected script
// could read it. A page reload loses it, and the refresh cookie silently gets a new one.
let accessToken: string | null = null

export function setAccessToken(token: string | null): void {
  accessToken = token
}

let onSessionLost: (() => void) | null = null

/** Called when the session cannot be refreshed, so the app can show the login screen. */
export function setSessionLostHandler(handler: (() => void) | null): void {
  onSessionLost = handler
}

let inFlightRefresh: Promise<string | null> | null = null

/**
 * Trade the httpOnly refresh cookie for a new access token. Returns null when signed out.
 *
 * Single-flight in this tab, and serialised across tabs with a Web Lock: two tabs refreshing
 * with the same cookie at once would look like token theft to the server and end the session.
 */
export function refreshAccessToken(): Promise<string | null> {
  inFlightRefresh ??= (async () => {
    try {
      const refresh = () => fetch(`${API_BASE}/auth/refresh`, { method: 'POST' })
      const response = navigator.locks
        ? await navigator.locks.request('lifepilot-auth-refresh', refresh)
        : await refresh()
      if (!response.ok) {
        accessToken = null
        return null
      }
      const body = (await response.json()) as TokenResponse
      accessToken = body.access_token
      return accessToken
    } catch {
      accessToken = null
      return null
    } finally {
      inFlightRefresh = null
    }
  })()
  return inFlightRefresh
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const send = (token: string | null) =>
    fetch(`${API_BASE}${path}`, {
      ...init,
      headers: {
        ...(init.body !== undefined ? { 'Content-Type': 'application/json' } : {}),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...init.headers,
      },
    })

  let response = await send(accessToken)

  // An expired access token: refresh once and retry. Auth endpoints are excluded, so a wrong
  // password on /auth/login is reported as such instead of triggering a refresh.
  if (response.status === 401 && !path.startsWith('/auth/')) {
    const fresh = await refreshAccessToken()
    if (fresh) {
      response = await send(fresh)
    }
    if (response.status === 401) {
      onSessionLost?.()
    }
  }

  if (!response.ok) throw await toApiError(response)
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}
