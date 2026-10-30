import { useState, type FormEvent } from 'react'
import Alert from '../Alert'
import Badge from '../Badge'
import Button from '../Button'
import Spinner from '../Spinner'
import { ApiError, api, type Booking } from '../../lib/api'

/*
  Price breakdown + technician estimate (merged feature).
  - Technician: after accepting, send labour + materials. Customer must approve before paying.
  - Customer: approve or decline. The platform fee is shown for transparency (sandbox — nothing is collected).
*/

function money(n: number | null, currency: string) {
  if (n == null) return '—'
  try {
    return new Intl.NumberFormat(undefined, { style: 'currency', currency, maximumFractionDigits: 2 }).format(n)
  } catch {
    return `${currency} ${n}`
  }
}

const STATUS = {
  listed_rate: { label: 'Listed rate', tone: 'navy' },
  proposed: { label: 'Estimate waiting for approval', tone: 'amber' },
  approved: { label: 'Estimate approved', tone: 'teal' },
  declined: { label: 'Estimate declined', tone: 'red' },
} as const

export default function EstimatePanel({ booking, onUpdated }: { booking: Booking; onUpdated: (b: Booking) => void }) {
  const pb = booking.price_breakdown
  const actions = booking.estimate_actions
  const [labour, setLabour] = useState(pb.labour ? String(pb.labour) : '')
  const [materials, setMaterials] = useState(pb.materials ? String(pb.materials) : '')
  const [note, setNote] = useState('')
  const [reason, setReason] = useState('')
  const [open, setOpen] = useState<'propose' | 'decline' | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)

  const run = async (fn: () => Promise<Booking>) => {
    setBusy(true)
    setError(null)
    try {
      onUpdated(await fn())
      setOpen(null)
    } catch (err) {
      setError(err instanceof ApiError ? err : new ApiError(0, 'unknown', 'Something went wrong.'))
    } finally {
      setBusy(false)
    }
  }

  const submitEstimate = (e: FormEvent) => {
    e.preventDefault()
    void run(() => api.proposeEstimate(booking.id, { labour: Number(labour || 0), materials: Number(materials || 0), note: note.trim() || undefined }))
  }

  const inputClass =
    'mt-1 block h-10 w-full rounded-lg border border-navy-900/20 bg-white px-3 text-base text-navy-900 focus:border-teal-600 focus:outline-2 focus:outline-teal-600'

  return (
    <section className="rounded-2xl border border-navy-900/10 bg-white p-5 sm:p-6" aria-labelledby="price-heading">
      <div className="flex flex-wrap items-center gap-2">
        <h2 id="price-heading" className="font-semibold text-navy-900">
          Price
        </h2>
        <Badge tone={STATUS[pb.status].tone}>{STATUS[pb.status].label}</Badge>
      </div>
      <dl className="mt-3 grid grid-cols-[1fr_auto] gap-x-4 gap-y-1 text-sm">
        <dt className="text-navy-600">Visit / consultation fee</dt>
        <dd className="text-right text-navy-900">{money(pb.visit_fee, pb.currency)}</dd>
        {pb.status !== 'listed_rate' && (
          <>
            <dt className="text-navy-600">Labour (estimate)</dt>
            <dd className="text-right text-navy-900">{money(pb.labour, pb.currency)}</dd>
            <dt className="text-navy-600">Materials (estimate)</dt>
            <dd className="text-right text-navy-900">{money(pb.materials, pb.currency)}</dd>
          </>
        )}
        <dt className="border-t border-navy-900/10 pt-1 font-semibold text-navy-900">Total</dt>
        <dd className="border-t border-navy-900/10 pt-1 text-right font-semibold text-navy-900">{money(pb.total, pb.currency)}</dd>
        <dt className="text-xs text-navy-600">Platform fee ({pb.commission_percent}% of fee + labour, sandbox)</dt>
        <dd className="text-right text-xs text-navy-600">{money(pb.platform_fee, pb.currency)}</dd>
        <dt className="text-xs text-navy-600">Technician receives</dt>
        <dd className="text-right text-xs text-navy-600">{money(pb.technician_earnings, pb.currency)}</dd>
      </dl>
      {pb.estimate_note && <p className="mt-3 rounded-lg bg-navy-50 p-3 text-sm text-navy-800">Technician’s note: {pb.estimate_note}</p>}
      <p className="mt-3 text-xs text-navy-600">{pb.note}</p>

      {error && (
        <div className="mt-3">
          <Alert tone="error" announce title="That didn’t work">
            {error.message}
            {error.details.length > 0 && ` ${error.details.map((d) => d.message).join(' ')}`}
          </Alert>
        </div>
      )}

      {actions.includes('propose') && open !== 'propose' && (
        <Button variant="secondary" className="mt-4" onClick={() => setOpen('propose')}>
          {pb.status === 'listed_rate' ? 'Send an estimate' : 'Send a new estimate'}
        </Button>
      )}
      {open === 'propose' && (
        <form onSubmit={submitEstimate} className="mt-4 space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <label className="text-sm font-medium text-navy-900">
              Labour ({pb.currency})
              <input type="number" min={0} inputMode="numeric" value={labour} onChange={(e) => setLabour(e.target.value)} className={inputClass} />
            </label>
            <label className="text-sm font-medium text-navy-900">
              Materials ({pb.currency})
              <input type="number" min={0} inputMode="numeric" value={materials} onChange={(e) => setMaterials(e.target.value)} className={inputClass} />
            </label>
          </div>
          <label className="block text-sm font-medium text-navy-900">
            What’s included <span className="font-normal text-navy-600">(optional)</span>
            <input value={note} maxLength={300} onChange={(e) => setNote(e.target.value)} className={inputClass} />
          </label>
          <div className="flex gap-2">
            <Button type="submit" disabled={busy}>
              {busy && <Spinner />} Send estimate
            </Button>
            <Button variant="secondary" onClick={() => setOpen(null)} disabled={busy}>
              Cancel
            </Button>
          </div>
        </form>
      )}

      {actions.includes('approve') && open !== 'decline' && (
        <div className="mt-4 flex flex-wrap gap-2">
          <Button onClick={() => void run(() => api.decideEstimate(booking.id, true))} disabled={busy}>
            {busy && <Spinner />} Approve estimate
          </Button>
          <Button variant="secondary" onClick={() => setOpen('decline')} disabled={busy}>
            Decline
          </Button>
        </div>
      )}
      {open === 'decline' && (
        <div className="mt-4 space-y-2">
          <label className="block text-sm font-medium text-navy-900">
            Reason <span className="font-normal text-navy-600">(optional, shared with the technician)</span>
            <input value={reason} maxLength={300} onChange={(e) => setReason(e.target.value)} className={inputClass} />
          </label>
          <div className="flex gap-2">
            <Button onClick={() => void run(() => api.decideEstimate(booking.id, false, reason))} disabled={busy}>
              Decline estimate
            </Button>
            <Button variant="secondary" onClick={() => setOpen(null)} disabled={busy}>
              Back
            </Button>
          </div>
        </div>
      )}
    </section>
  )
}
