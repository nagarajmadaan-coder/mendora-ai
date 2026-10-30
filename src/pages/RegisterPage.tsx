import { useEffect, useRef, useState, type ChangeEvent, type FormEvent } from 'react'
import AuthCard from '../components/AuthCard'
import TextField from '../components/TextField'
import Button from '../components/Button'
import Alert from '../components/Alert'
import Spinner from '../components/Spinner'
import { Link, useRouter } from '../lib/router'
import { ApiError } from '../lib/api'
import { ROUTES, safeNextPath } from '../data/content'
import { useAuth } from '../state/AuthContext'

const PASSWORD_MIN = 8 // same rule as the backend (backend/app/schemas.py)
const EMAIL_SHAPE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

type Field = 'full_name' | 'email' | 'password' | 'confirm'

/* Create a customer account (URL: /register). Technician and admin accounts can't be created here. */
export default function RegisterPage() {
  const { location, replace } = useRouter()
  const { register, status } = useAuth()
  const params = new URLSearchParams(location.search)
  const next = safeNextPath(params.get('next'))

  const [form, setForm] = useState({ full_name: '', email: '', password: '', confirm: '' })
  const [errors, setErrors] = useState<Partial<Record<Field, string>>>({})
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const refs = {
    full_name: useRef<HTMLInputElement>(null),
    email: useRef<HTMLInputElement>(null),
    password: useRef<HTMLInputElement>(null),
    confirm: useRef<HTMLInputElement>(null),
  }

  useEffect(() => {
    if (status === 'signedIn') replace(next)
  }, [status, next, replace])

  const set = (field: Field) => (e: ChangeEvent<HTMLInputElement>) => setForm((f) => ({ ...f, [field]: e.target.value }))

  function validate(): Partial<Record<Field, string>> {
    const errs: Partial<Record<Field, string>> = {}
    if (!form.full_name.trim()) errs.full_name = 'Please enter your name.'
    if (!EMAIL_SHAPE.test(form.email.trim())) errs.email = 'Please enter a valid email address.'
    if (form.password.length < PASSWORD_MIN) errs.password = `Use at least ${PASSWORD_MIN} characters.`
    else if (!form.password.trim()) errs.password = 'Password can’t be only spaces.'
    if (form.confirm !== form.password) errs.confirm = 'Passwords don’t match.'
    return errs
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    const errs = validate()
    setErrors(errs)
    setError(null)
    const first = (['full_name', 'email', 'password', 'confirm'] as Field[]).find((f) => errs[f])
    if (first) {
      refs[first].current?.focus()
      return
    }
    setBusy(true)
    try {
      await register(form.email.trim(), form.password, form.full_name.trim())
      replace(next)
    } catch (err) {
      if (err instanceof ApiError) {
        // Show server-side field messages next to the right field.
        const serverErrs: Partial<Record<Field, string>> = {
          full_name: err.fieldMessage('full_name'),
          email: err.fieldMessage('email') ?? (err.code === 'email_taken' ? err.message : undefined),
          password: err.fieldMessage('password'),
        }
        setErrors(serverErrs)
        if (!Object.values(serverErrs).some(Boolean)) setError(err.message)
      } else {
        setError('Something went wrong. Please try again.')
      }
    } finally {
      setBusy(false)
    }
  }

  return (
    <AuthCard
      title="Create an account"
      documentTitle="Create an account"
      intro="An account keeps your repair requests private and lets you get AI diagnoses."
    >
      <form noValidate onSubmit={handleSubmit} className="space-y-5">
        {error && <Alert tone="error" announce title={error} />}
        <TextField ref={refs.full_name} id="reg-name" label="Full name" autoComplete="name" value={form.full_name} onChange={set('full_name')} error={errors.full_name} />
        <TextField ref={refs.email} id="reg-email" label="Email" type="email" autoComplete="email" value={form.email} onChange={set('email')} error={errors.email} />
        <TextField
          ref={refs.password}
          id="reg-password"
          label="Password"
          type="password"
          autoComplete="new-password"
          hint={`At least ${PASSWORD_MIN} characters. A short phrase is easy to remember and hard to guess.`}
          value={form.password}
          onChange={set('password')}
          error={errors.password}
        />
        <TextField ref={refs.confirm} id="reg-confirm" label="Confirm password" type="password" autoComplete="new-password" value={form.confirm} onChange={set('confirm')} error={errors.confirm} />
        <Button type="submit" size="lg" className="w-full" disabled={busy}>
          {busy ? (
            <>
              <Spinner label="Creating account" /> Creating account…
            </>
          ) : (
            'Create account'
          )}
        </Button>
      </form>
      <p className="mt-6 border-t border-navy-900/10 pt-5 text-center text-sm text-navy-700">
        Already have an account?{' '}
        <Link to={`${ROUTES.login}${location.search}`} className="rounded font-semibold text-teal-800 underline underline-offset-2 hover:text-teal-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-600">
          Sign in
        </Link>
      </p>
    </AuthCard>
  )
}
