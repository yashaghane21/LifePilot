import { createContext, useContext } from 'react'
import type { Appearance, ResolvedTheme } from './theme'

export interface AppearanceContextValue {
  appearance: Appearance
  /** The theme actually shown: `system` resolved to light or dark. */
  resolved: ResolvedTheme
  update: (patch: Partial<Appearance>) => void
}

export const AppearanceContext = createContext<AppearanceContextValue | null>(null)

export function useAppearance(): AppearanceContextValue {
  const value = useContext(AppearanceContext)
  if (!value) throw new Error('useAppearance must be used inside <ThemeProvider>')
  return value
}
