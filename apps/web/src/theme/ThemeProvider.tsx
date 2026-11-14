import { useCallback, useEffect, useMemo, useState, useSyncExternalStore, type ReactNode } from 'react'
import { AppearanceContext } from './context'
import { applyTheme, loadAppearance, saveAppearance, type Appearance, type ResolvedTheme } from './theme'

const DARK_QUERY = '(prefers-color-scheme: dark)'

function subscribeToSystemTheme(onChange: () => void): () => void {
  const media = window.matchMedia(DARK_QUERY)
  media.addEventListener('change', onChange)
  return () => media.removeEventListener('change', onChange)
}

function systemPrefersDark(): boolean {
  return window.matchMedia(DARK_QUERY).matches
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [appearance, setAppearance] = useState<Appearance>(loadAppearance)
  // Re-renders when the OS switches between light and dark, so "System" follows it live.
  const systemDark = useSyncExternalStore(subscribeToSystemTheme, systemPrefersDark)
  const resolved: ResolvedTheme =
    appearance.mode === 'system' ? (systemDark ? 'dark' : 'light') : appearance.mode

  useEffect(() => {
    applyTheme(resolved, appearance.accent)
  }, [resolved, appearance.accent])

  useEffect(() => {
    saveAppearance(appearance)
  }, [appearance])

  const update = useCallback((patch: Partial<Appearance>) => {
    setAppearance((current) => ({ ...current, ...patch }))
  }, [])

  const value = useMemo(() => ({ appearance, resolved, update }), [appearance, resolved, update])

  return <AppearanceContext value={value}>{children}</AppearanceContext>
}
