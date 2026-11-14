import type { ReactNode } from 'react'
import { Icon } from '../../components/ui/Icon'

interface AuthLayoutProps {
  title: string
  subtitle: string
  children: ReactNode
  footer: ReactNode
}

/** Centred, minimal frame shared by the login and register pages. */
export function AuthLayout({ title, subtitle, children, footer }: AuthLayoutProps) {
  return (
    <main className="flex min-h-screen items-center justify-center bg-canvas px-4 py-10">
      <div className="flex w-full max-w-sm flex-col gap-6">
        <div className="flex flex-col items-center gap-3 text-center">
          <Icon name="logo" size={40} className="text-accent" />
          <h1 className="m-0 text-2xl font-semibold tracking-tight">{title}</h1>
          <p className="m-0 text-sm text-muted">{subtitle}</p>
        </div>
        {children}
        <p className="m-0 text-center text-sm text-muted">{footer}</p>
      </div>
    </main>
  )
}

interface FieldProps {
  id: string
  label: string
  type: string
  autoComplete: string
  value: string
  onChange: (value: string) => void
  error?: string
  hint?: string
  minLength?: number
}

export function Field({ id, label, type, autoComplete, value, onChange, error, hint, minLength }: FieldProps) {
  const describedBy = error ? `${id}-error` : hint ? `${id}-hint` : undefined
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-sm font-medium">
        {label}
      </label>
      <input
        id={id}
        name={id}
        type={type}
        autoComplete={autoComplete}
        required
        minLength={minLength}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy}
        className={`h-11 rounded-xl border bg-surface px-3.5 text-[15px] text-ink outline-none focus:border-accent ${
          error ? 'border-danger' : 'border-line'
        }`}
      />
      {error ? (
        <span id={`${id}-error`} className="text-xs text-danger">
          {error}
        </span>
      ) : (
        hint && (
          <span id={`${id}-hint`} className="text-xs text-muted">
            {hint}
          </span>
        )
      )}
    </div>
  )
}

export function SubmitButton({ busy, children }: { busy: boolean; children: ReactNode }) {
  return (
    <button
      type="submit"
      disabled={busy}
      className="h-11 cursor-pointer rounded-xl border-none bg-accent text-[15px] font-semibold text-on-accent hover:bg-accent-hover disabled:cursor-wait disabled:opacity-60"
    >
      {busy ? 'Please wait…' : children}
    </button>
  )
}

/**
 * A full-page navigation (not fetch): the browser must visit Google itself.
 * `next` is where to land afterwards; the backend accepts only in-app paths.
 */
export function GoogleButton({ next = '/' }: { next?: string }) {
  return (
    <a
      href={`/api/v1/auth/google/start?next=${encodeURIComponent(next)}`}
      className="flex h-11 items-center justify-center gap-3 rounded-xl border border-line bg-surface text-[15px] font-semibold text-ink no-underline hover:bg-bubble"
    >
      {/* Google's "G" mark, as its sign-in branding guidelines require. */}
      <svg aria-hidden="true" width="18" height="18" viewBox="0 0 48 48">
        <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z" />
        <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z" />
        <path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z" />
        <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z" />
      </svg>
      Continue with Google
    </a>
  )
}

export function OrDivider() {
  return (
    <div className="flex items-center gap-3 text-xs text-muted" aria-hidden="true">
      <span className="h-px flex-1 bg-line" />
      or
      <span className="h-px flex-1 bg-line" />
    </div>
  )
}

export function FormError({ message }: { message: string | null }) {
  if (!message) return null
  return (
    <p role="alert" className="m-0 rounded-xl border border-warning-line bg-warning-soft px-3.5 py-2.5 text-sm text-warning">
      {message}
    </p>
  )
}
