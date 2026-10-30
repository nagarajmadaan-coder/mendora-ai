import { useEffect, useRef, useState } from 'react'
import Alert from '../Alert'
import Badge from '../Badge'
import Button from '../Button'
import Icon from '../Icon'
import Spinner from '../Spinner'
import { ApiError, api, type Booking, type Payment, type PaymentResult, type SandboxScenario } from '../../lib/api'

/*
  SANDBOX payment for one booking (Step 10).
  - No card details are asked for or sent. The tester picks which outcome to simulate.
  - Success/failure shown here is exactly what the server's simulated payment returned.
  - Double clicks and network retries reuse the same "idempotency key", so the server never
    charges twice; a new key is made only after a definite answer.
*/

const SCENARIOS: { value: SandboxScenario; label: string }[] = [
  { value: 'success', label: 'Successful payment' },
  { value: 'card_declined', label: 'Card declined' },
  { value: 'insufficient_funds', label: 'Insufficient funds' },
  { value: 'processing_error', label: 'Provider error (temporary)' },
]

const STATUS = {
  paid: { label: 'Paid (sandbox)', tone: 'teal' },
  unpaid: { label: 'Payment due', tone: 'amber' },
  refunded: { label: 'Refunded (sandbox)', tone: 'navy' },
  not_payable: { label: 'Not payable yet', tone: 'navy' },
} as const

function newKey(): string {
  const random = typeof crypto !== 'undefined' && 'randomUUID' in crypto ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(36).slice(2)}`
  return `pay-${random}`.replace(/[^A-Za-z0-9_-]/g, '').slice(0, 64)
}

function money(amount: number | null, currency: string): string {
  if (amount == null) return 'Price to be confirmed'
  try {
    return new Intl.NumberFormat(undefined, { style: 'currency', currency, maximumFractionDigits: 0 }).format(amount)
  } catch {
    return `${currency} ${amount}`
  }
}

interface Props {
  booking: Booking
  /** Called after a payment attempt so the page reloads the booking (status, history). */
  onChanged: () => void
  showHistory: boolean
}

export default function PaymentPanel({ booking, onChanged, showHistory }: Props) {
  const pay = booking.payment
  const [step, setStep] = useState<'idle' | 'review'>('idle')
  const [scenario, setScenario] = useState<SandboxScenario>('success')
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<PaymentResult | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [history, setHistory] = useState<Payment[] | null>(null)
  const keyRef = useRef<string>(newKey())

  useEffect(() => {
    if (!showHistory) return
    let cancelled = false
    api
      .listBookingPayments(booking.id)
      .then((r) => !cancelled && setHistory(r.payments))
      .catch(() => !cancelled && setHistory(null))
    return () => {
      cancelled = true
    }
  }, [booking.id, booking.updated_at, result, showHistory])

  const submit = async () => {
    if (busy || pay.amount == null) return // ignore repeated clicks while a payment is in progress
    setBusy(true)
    setError(null)
    try {
      const r = await api.payBooking(booking.id, {
        expected_amount: pay.amount,
        currency: pay.currency,
        scenario,
        idempotency_key: keyRef.current,
      })
      setResult(r)
      keyRef.current = newKey() // definite answer → the next attempt is a new one
      setStep('idle')
      onChanged()
    } catch (err) {
      const e = err instanceof ApiError ? err : new ApiError(0, 'unknown', 'Something went wrong.')
      setError(e)
      // Network problem: keep the same key, so "Try again" can't pay twice. Any server answer: new key.
      if (e.status !== 0) keyRef.current = newKey()
      if (e.code === 'amount_mismatch' || e.code === 'already_paid' || e.code === 'booking_not_payable') {
        setStep('idle')
        onChanged()
      }
    } finally {
      setBusy(false)
    }
  }

  const badge = STATUS[pay.status]

  return (
    <section className="rounded-2xl border border-navy-900/10 bg-white p-5" aria-labelledby="payment-heading" aria-live="polite">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="payment-heading" className="font-semibold text-navy-900">
          Payment
        </h2>
        <Badge tone={badge.tone}>{badge.label}</Badge>
      </div>
      <p className="mt-3 flex items-start gap-2 rounded-lg bg-amber-50 p-3 text-xs leading-relaxed text-amber-900 ring-1 ring-inset ring-amber-700/20">
        <Icon name="info" className="mt-px size-3.5 shrink-0" />
        {pay.sandbox_notice}
      </p>

      {result && (
        <div className="mt-3">
          <Alert tone={result.payment.status === 'succeeded' ? 'success' : 'error'} announce title={result.payment.status === 'succeeded' ? 'Payment succeeded' : 'Payment failed'}>
            {result.message}
            {result.payment.transaction_ref && <span className="mt-1 block text-xs">Simulated reference: {result.payment.transaction_ref}</span>}
          </Alert>
        </div>
      )}
      {error && (
        <div className="mt-3">
          <Alert
            tone="error"
            announce
            title={error.status === 0 ? 'Couldn’t reach the server' : 'Payment not made'}
            action={
              error.status === 0 ? (
                <Button variant="secondary" onClick={() => void submit()} disabled={busy}>
                  Try again
                </Button>
              ) : undefined
            }
          >
            {error.message}
            {error.status === 0 && ' Trying again is safe: you won’t be charged twice.'}
          </Alert>
        </div>
      )}

      {pay.status === 'paid' && !result && <p className="mt-3 text-sm text-navy-700">This booking has been paid in the sandbox.</p>}
      {pay.status === 'refunded' && <p className="mt-3 text-sm text-navy-700">The sandbox payment was refunded because the booking was cancelled.</p>}
      {!pay.can_pay && pay.reason && pay.status !== 'paid' && pay.status !== 'refunded' && <p className="mt-3 text-sm text-navy-700">{pay.reason}</p>}
      {pay.payout_note && (
        <p className="mt-3 flex items-start gap-2 rounded-lg bg-navy-50 p-3 text-xs leading-relaxed text-navy-800">
          <Icon name="shield" className="mt-px size-3.5 shrink-0" />
          {pay.payout_note}
        </p>
      )}

      {pay.can_pay && step === 'idle' && (
        <Button
          className="mt-4 w-full"
          onClick={() => {
            setScenario('success')
            setResult(null)
            setError(null)
            setStep('review')
          }}
        >
          <Icon name="lock" className="size-4" />
          Pay {money(pay.amount, pay.currency)} (sandbox)
        </Button>
      )}

      {pay.can_pay && step === 'review' && (
        <div className="mt-4 space-y-3">
          <dl className="space-y-1 rounded-lg bg-navy-50 p-3 text-sm">
            <div className="flex justify-between gap-3">
              <dt className="text-navy-600">For</dt>
              <dd className="text-right font-medium text-navy-900">{booking.booking_type === 'technician_visit' ? 'Technician visit' : 'Expert consultation'}</dd>
            </div>
            <div className="flex justify-between gap-3">
              <dt className="text-navy-600">With</dt>
              <dd className="text-right font-medium text-navy-900">{booking.technician.display_name}</dd>
            </div>
            <div className="flex justify-between gap-3">
              <dt className="text-navy-600">When</dt>
              <dd className="text-right font-medium text-navy-900">{booking.local_time_label}</dd>
            </div>
            <div className="flex justify-between gap-3 border-t border-navy-900/10 pt-1">
              <dt className="font-semibold text-navy-900">Amount</dt>
              <dd className="font-semibold text-navy-900">{money(pay.amount, pay.currency)}</dd>
            </div>
          </dl>
          <fieldset>
            <legend className="text-sm font-semibold text-navy-900">Sandbox: outcome to simulate</legend>
            <div className="mt-2 space-y-1.5">
              {SCENARIOS.map((s) => (
                <label key={s.value} className="flex items-center gap-2 text-sm text-navy-800">
                  <input type="radio" name="scenario" checked={scenario === s.value} onChange={() => setScenario(s.value)} className="accent-teal-700" />
                  {s.label}
                </label>
              ))}
            </div>
          </fieldset>
          <p className="text-xs text-navy-600">No card details are needed or collected.</p>
          <div className="flex flex-col gap-2">
            <Button onClick={() => void submit()} disabled={busy}>
              {busy ? <Spinner /> : <Icon name="check" className="size-4" />}
              {busy ? 'Processing…' : `Confirm sandbox payment of ${money(pay.amount, pay.currency)}`}
            </Button>
            <Button variant="secondary" onClick={() => setStep('idle')} disabled={busy}>
              Back
            </Button>
          </div>
        </div>
      )}

      {showHistory && history && history.length > 0 && (
        <div className="mt-5">
          <h3 className="text-sm font-semibold text-navy-900">Payment attempts</h3>
          <ul className="mt-2 space-y-1.5 text-xs text-navy-700">
            {history.map((p) => (
              <li key={p.id} className="flex flex-wrap justify-between gap-x-3 rounded-md bg-navy-50 px-2.5 py-1.5">
                <span className="font-medium text-navy-900">
                  {p.status === 'succeeded' ? 'Succeeded' : p.status === 'failed' ? 'Failed' : p.status === 'refunded' ? 'Refunded' : 'Pending'}
                  {p.failure_code ? ` — ${p.failure_code.replace(/_/g, ' ')}` : ''}
                </span>
                <span>
                  {money(p.amount, p.currency)} · {new Date(p.created_at).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  )
}
