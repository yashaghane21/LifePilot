import { createContext, useContext } from 'react'
import type { RegisterRequest, User } from '../api/types'

export type AuthState =
  | { status: 'loading' }
  | { status: 'anonymous' }
  | { status: 'authenticated'; user: User }

export interface AuthContextValue {
  state: AuthState
  login: (email: string, password: string) => Promise<void>
  register: (data: RegisterRequest) => Promise<void>
  logout: () => Promise<void>
}

export const AuthContext = createContext<AuthContextValue | null>(null)

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext)
  if (!value) throw new Error('useAuth must be used inside <AuthProvider>')
  return value
}

/** The signed-in user. Only call inside routes wrapped by <RequireAuth>. */
export function useCurrentUser(): User {
  const { state } = useAuth()
  if (state.status !== 'authenticated') throw new Error('useCurrentUser used outside a signed-in route')
  return state.user
}
