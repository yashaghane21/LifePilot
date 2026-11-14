import { apiFetch, refreshAccessToken, setAccessToken } from './http'
import type { RegisterRequest, TokenResponse, User } from './types'

export const authApi = {
  register: (body: RegisterRequest) =>
    apiFetch<User>('/auth/register', { method: 'POST', body: JSON.stringify(body) }),

  /** Sets the in-memory access token; the server sets the refresh cookie. */
  async login(email: string, password: string): Promise<void> {
    const token = await apiFetch<TokenResponse>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    })
    setAccessToken(token.access_token)
  },

  async logout(): Promise<void> {
    try {
      await apiFetch<void>('/auth/logout', { method: 'POST' })
    } finally {
      setAccessToken(null)
    }
  },

  me: () => apiFetch<User>('/users/me'),

  /** On page load: use the refresh cookie, if any, to get an access token. */
  restoreSession: refreshAccessToken,
}
