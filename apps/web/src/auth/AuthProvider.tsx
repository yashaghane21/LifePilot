import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { authApi } from '../api/auth'
import { setSessionLostHandler } from '../api/http'
import type { RegisterRequest } from '../api/types'
import { AuthContext, type AuthState } from './context'

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({ status: 'loading' })

  // On page load, try the refresh cookie: a returning user is signed in without typing anything.
  useEffect(() => {
    let cancelled = false
    ;(async () => {
      const token = await authApi.restoreSession()
      if (!token) {
        if (!cancelled) setState({ status: 'anonymous' })
        return
      }
      try {
        const user = await authApi.me()
        if (!cancelled) setState({ status: 'authenticated', user })
      } catch {
        if (!cancelled) setState({ status: 'anonymous' })
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  // If a later API call finds the session gone (revoked, expired), show the login screen.
  useEffect(() => {
    setSessionLostHandler(() => setState({ status: 'anonymous' }))
    return () => setSessionLostHandler(null)
  }, [])

  const login = useCallback(async (email: string, password: string) => {
    await authApi.login(email, password)
    const user = await authApi.me()
    setState({ status: 'authenticated', user })
  }, [])

  const register = useCallback(
    async (data: RegisterRequest) => {
      await authApi.register(data)
      await login(data.email, data.password)
    },
    [login],
  )

  const logout = useCallback(async () => {
    try {
      await authApi.logout()
    } finally {
      setState({ status: 'anonymous' })
    }
  }, [])

  const value = useMemo(() => ({ state, login, register, logout }), [state, login, register, logout])

  return <AuthContext value={value}>{children}</AuthContext>
}
