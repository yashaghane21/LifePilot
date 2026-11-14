export type ThemeMode = 'light' | 'dark' | 'system'
export type ResolvedTheme = 'light' | 'dark'
export type AccentName = 'green' | 'blue' | 'violet' | 'amber'

export interface Appearance {
  mode: ThemeMode
  accent: AccentName
}

interface AccentShade {
  accent: string
  hover: string
  /** Text/icon colour placed on top of the accent (buttons). */
  onAccent: string
}

/**
 * Each accent has a light-theme and a dark-theme shade, both checked for ≥4.5:1 contrast:
 * the accent against the page, and `onAccent` against the accent.
 */
export const ACCENTS: Record<AccentName, { label: string; light: AccentShade; dark: AccentShade }> = {
  green: {
    label: 'Green',
    light: { accent: '#15803d', hover: '#166534', onAccent: '#ffffff' },
    dark: { accent: '#22c55e', hover: '#4ade80', onAccent: '#052e16' },
  },
  blue: {
    label: 'Blue',
    light: { accent: '#2563eb', hover: '#1d4ed8', onAccent: '#ffffff' },
    dark: { accent: '#60a5fa', hover: '#93c5fd', onAccent: '#0b1b33' },
  },
  violet: {
    label: 'Violet',
    light: { accent: '#7c3aed', hover: '#6d28d9', onAccent: '#ffffff' },
    dark: { accent: '#a78bfa', hover: '#c4b5fd', onAccent: '#1e1033' },
  },
  amber: {
    label: 'Amber',
    light: { accent: '#b45309', hover: '#92400e', onAccent: '#ffffff' },
    dark: { accent: '#fbbf24', hover: '#fcd34d', onAccent: '#2a1a05' },
  },
}

export const DEFAULT_APPEARANCE: Appearance = { mode: 'system', accent: 'green' }

// Also read by the inline script in index.html; keep the key in sync.
const STORAGE_KEY = 'lifepilot.appearance'

const THEME_MODES: readonly ThemeMode[] = ['light', 'dark', 'system']

/** Stored appearance, falling back to defaults for anything missing or invalid. */
export function loadAppearance(): Appearance {
  try {
    const raw: unknown = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '{}')
    const stored = (raw && typeof raw === 'object' ? raw : {}) as Record<string, unknown>
    return {
      mode: THEME_MODES.includes(stored.mode as ThemeMode) ? (stored.mode as ThemeMode) : DEFAULT_APPEARANCE.mode,
      accent:
        typeof stored.accent === 'string' && Object.hasOwn(ACCENTS, stored.accent)
          ? (stored.accent as AccentName)
          : DEFAULT_APPEARANCE.accent,
    }
  } catch {
    return DEFAULT_APPEARANCE
  }
}

export function saveAppearance(appearance: Appearance): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(appearance))
  } catch {
    // Storage unavailable (private mode, blocked): the choice lasts for this visit only.
  }
}

/** Switch the page's colour variables; every component follows automatically. */
export function applyTheme(theme: ResolvedTheme, accent: AccentName): void {
  const root = document.documentElement
  const shade = ACCENTS[accent][theme]
  root.dataset.theme = theme
  root.style.setProperty('--lp-accent', shade.accent)
  root.style.setProperty('--lp-accent-hover', shade.hover)
  root.style.setProperty('--lp-on-accent', shade.onAccent)
}
