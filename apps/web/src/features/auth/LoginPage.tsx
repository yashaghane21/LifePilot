import { useState, type FormEvent } from 'react'
import { Link, useLocation, useSearchParams } from 'react-router'
import { ApiError } from '../../api/http'
import { useAuth } from '../../auth/context'
import { AuthLayout, Field, FormError, GoogleButton, OrDivider, SubmitButton } from './AuthLayout'
import { GOOGLE_ERROR_MESSAGES } from './googleErrors'

export function LoginPage() {
  const { login } = useAuth()
  const location = useLocation()
  const [searchParams] = useSearchParams()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  // A failed Google sign-in lands here as /login?error=<code>.
  const googleError = searchParams.get('error')
  const [error, setError] = useState<string | null>(
    googleError ? (GOOGLE_ERROR_MESSAGES[googleError] ?? GOOGLE_ERROR_MESSAGES.google_failed) : null,
  )
  const [busy, setBusy] = useState(false)
  const from = (location.state as { from?: string } | null)?.from ?? '/'

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      // On success the auth state changes and <PublicOnly> navigates onward.
      await login(email, password)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not reach LifePilot. Is the backend running?')
      setBusy(false)
    }
  }

  return (
    <AuthLayout
      title="Welcome back"
      subtitle="Sign in to LifePilot"
      footer={
        <>
          New here?{' '}
          <Link to="/register" className="font-medium text-accent hover:text-accent-hover">
            Create an account
          </Link>
        </>
      }
    >
      <FormError message={error} />
      <GoogleButton next={from} />
      <OrDivider />
      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        <Field id="email" label="Email" type="email" autoComplete="email" value={email} onChange={setEmail} />
        <Field
          id="password"
          label="Password"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={setPassword}
        />
        <SubmitButton busy={busy}>Sign in</SubmitButton>
      </form>
    </AuthLayout>
  )
}
