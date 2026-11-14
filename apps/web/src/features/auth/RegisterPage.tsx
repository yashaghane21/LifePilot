import { useState, type FormEvent } from 'react'
import { Link } from 'react-router'
import { ApiError } from '../../api/http'
import { useAuth } from '../../auth/context'
import { AuthLayout, Field, FormError, GoogleButton, OrDivider, SubmitButton } from './AuthLayout'

const MIN_PASSWORD_LENGTH = 12 // must match the backend's NewPassword rule

export function RegisterPage() {
  const { register } = useAuth()
  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [formError, setFormError] = useState<string | null>(null)
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState(false)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setBusy(true)
    setFormError(null)
    setFieldErrors({})
    try {
      await register({ full_name: fullName, email, password })
    } catch (err) {
      if (err instanceof ApiError && err.code === 'validation_error') {
        setFieldErrors(err.fieldErrors())
      } else if (err instanceof ApiError) {
        setFormError(err.message)
      } else {
        setFormError('Could not reach LifePilot. Is the backend running?')
      }
      setBusy(false)
    }
  }

  return (
    <AuthLayout
      title="Create your account"
      subtitle="Your personal AI operating system"
      footer={
        <>
          Already have an account?{' '}
          <Link to="/login" className="font-medium text-accent hover:text-accent-hover">
            Sign in
          </Link>
        </>
      }
    >
      <GoogleButton />
      <OrDivider />
      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        <FormError message={formError} />
        <Field
          id="full_name"
          label="Name"
          type="text"
          autoComplete="name"
          value={fullName}
          onChange={setFullName}
          error={fieldErrors.full_name}
        />
        <Field
          id="email"
          label="Email"
          type="email"
          autoComplete="email"
          value={email}
          onChange={setEmail}
          error={fieldErrors.email}
        />
        <Field
          id="password"
          label="Password"
          type="password"
          autoComplete="new-password"
          minLength={MIN_PASSWORD_LENGTH}
          value={password}
          onChange={setPassword}
          error={fieldErrors.password}
          hint={`At least ${MIN_PASSWORD_LENGTH} characters. A short sentence works well.`}
        />
        <SubmitButton busy={busy}>Create account</SubmitButton>
      </form>
    </AuthLayout>
  )
}
