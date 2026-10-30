import { useEffect, useRef, useState, type FormEvent } from 'react'
import AuthCard from '../components/AuthCard'
import TextField from '../components/TextField'
import Button from '../components/Button'
import Alert from '../components/Alert'
import Spinner from '../components/Spinner'
import { Link, useRouter } from '../lib/router'
import { ApiError } from '../lib/api'
import { ROUTES, safeNextPath } from '../data/content'
import { useAuth } from '../state/AuthContext'

/*
  Sign in (URL: /login).
  ?next=/somewhere  → where to go after signing in (only pages inside this app are allowed)
  ?reason=diagnose  → shows why sign-in is needed
*/
export default function LoginPage() {
  const { location, replace } = useRouter()
  const { login, status, sessionExpired } = useAuth()
  const params = new URLSearchParams(location.search)
  const next = safeNextPath(params.get('next'))
  const reason = params.get('reason')

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [fieldErrors, setFieldErrors] = useState<{ email?: string; password?: string }>({})
  const [busy, setBusy] = useState(false)
  const emailRef = useRef<HTMLInputElement>(null)

  // Already signed in? Go straight on.
  useEffect(() => {
    if (status === 'signedIn') replace(next)
  }, [status, next, replace])

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    const errs: typeof fieldErrors = {}
    if (!email.trim()) errs.email = 'Please enter your email.'
    if (!password) errs.password = 'Please enter your password.'
    setFieldErrors(errs)
    setError(null)
    if (errs.email || errs.password) {
      emailRef.current?.focus()
      return
    }
    setBusy(true)
    try {
      await login(email.trim(), password)
      replace(next) // the effect above would also do this; replace keeps Back from returning to the form
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Something went wrong. Please try again.')
      setPassword('')
    } finally {
      setBusy(false)
    }
  }

  const registerLink = `${ROUTES.register}${location.search}`

  return (
    <AuthCard
      title="Sign in"
      documentTitle="Sign in"
      intro={
        reason === 'diagnose'
          ? 'Sign in to save your repair request and get an AI diagnosis. What you typed is kept.'
          : reason === 'book'
            ? 'Sign in to book a technician or an expert consultation.'
            : 'Welcome back. Sign in to see your repair requests.'
      }
    >
      <form noValidate onSubmit={handleSubmit} className="space-y-5">
        {error && <Alert tone="error" announce title={error} />}
        {!error && sessionExpired && (
          <Alert tone="warning" announce title="Your session has ended">
            For your security you were signed out. Please sign in again to continue.
          </Alert>
        )}
        <TextField
          ref={emailRef}
          id="login-email"
          label="Email"
          type="email"
          autoComplete="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          error={fieldErrors.email}
        />
        <TextField
          id="login-password"
          label="Password"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          error={fieldErrors.password}
        />
        <Button type="submit" size="lg" className="w-full" disabled={busy}>
          {busy ? (
            <>
              <Spinner label="Signing in" /> Signing in…
            </>
          ) : (
            'Sign in'
          )}
        </Button>
      </form>
      <p className="mt-6 border-t border-navy-900/10 pt-5 text-center text-sm text-navy-700">
        New to MENDORA?{' '}
        <Link to={registerLink} className="rounded font-semibold text-teal-800 underline underline-offset-2 hover:text-teal-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-600">
          Create an account
        </Link>
      </p>
    </AuthCard>
  )
}
