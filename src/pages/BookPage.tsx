import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react'
import PageHeader, { PageContainer } from '../components/PageHeader'
import Alert from '../components/Alert'
import Badge from '../components/Badge'
import Button from '../components/Button'
import Icon from '../components/Icon'
import Spinner from '../components/Spinner'
import { useRouter } from '../lib/router'
import {
  ApiError,
  api,
  type AvailabilityResult,
  type BookingInput,
  type BookingQuote,
  type BookingType,
  type RepairRequest,
  type Technician,
} from '../lib/api'
import { ROUTES, TRADES, bookingUrl, loginUrl, techniciansUrl } from '../data/content'
import { useAuth } from '../state/AuthContext'
import { TechnicianBadges, money } from './TechniciansPage'

/*
  Book a technician visit or an expert consultation (URL: /book?technician=…&type=…&request=…).
  1. Choose which of your saved repair requests it's for.
  2. Choose a date and a free time (or, for consultations, the next free slot).
  3. Review: the server returns the listed price, the time, and any safety warning.
  4. Confirm. High-risk requests need you to confirm you are safe first.
  Payment happens later, after the technician accepts (sandbox only — no real money). No live call is connected.
*/

function toApiError(err: unknown): ApiError {
  return err instanceof ApiError ? err : new ApiError(0, 'unknown', 'Something went wrong. Please try again.')
}

function localDateString(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

const TYPE_TEXT: Record<BookingType, { title: string; short: string }> = {
  technician_visit: { title: 'Request a technician visit', short: 'Technician visit (2 hours)' },
  expert_consultation: { title: 'Book an expert consultation', short: 'Expert consultation (30 minutes)' },
}

export default function BookPage() {
  const { location, replace, navigate } = useRouter()
  const { status, user } = useAuth()
  const params = useMemo(() => new URLSearchParams(location.search), [location.search])
  const technicianId = params.get('technician') ?? ''
  const initialType: BookingType = params.get('type') === 'expert_consultation' ? 'expert_consultation' : 'technician_visit'

  const [technician, setTechnician] = useState<Technician | null>(null)
  const [requests, setRequests] = useState<RepairRequest[] | null>(null)
  const [loadError, setLoadError] = useState<ApiError | null>(null)

  const [bookingType, setBookingType] = useState<BookingType>(initialType)
  const [requestId, setRequestId] = useState(params.get('request') ?? '')
  const [date, setDate] = useState(() => localDateString(new Date(Date.now() + 86_400_000)))
  const [availability, setAvailability] = useState<AvailabilityResult | null>(null)
  const [slotsError, setSlotsError] = useState<string | null>(null)
  const [slot, setSlot] = useState<string | null>(null)
  const [useNext, setUseNext] = useState(false)
  const [area, setArea] = useState('')
  const [address, setAddress] = useState('')
  const [note, setNote] = useState('')

  const [quote, setQuote] = useState<BookingQuote | null>(null)
  const [acknowledged, setAcknowledged] = useState(false)
  const [busy, setBusy] = useState<'quote' | 'confirm' | null>(null)
  const [formError, setFormError] = useState<ApiError | null>(null)
  const [slotsReload, setSlotsReload] = useState(0)

  // Only signed-in customers can book.
  useEffect(() => {
    if (status === 'signedOut') replace(loginUrl(`${location.pathname}${location.search}`, 'book'))
  }, [status, replace, location.pathname, location.search])

  // Load the technician and the customer's requests.
  useEffect(() => {
    if (status !== 'signedIn' || user?.role !== 'customer' || !technicianId) return
    let cancelled = false
    setLoadError(null)
    Promise.all([api.getTechnician(technicianId), api.listMyRepairRequests()])
      .then(([t, r]) => {
        if (cancelled) return
        setTechnician(t)
        const matching = r.items.filter((x) => x.trade.id === t.trade)
        setRequests(matching)
        setArea((a) => a || t.service_areas[0] || '')
        setRequestId((id) => (matching.some((x) => x.request_id === id) ? id : (matching[0]?.request_id ?? '')))
        if (!t.offers_consultation) setBookingType('technician_visit')
      })
      .catch((err) => !cancelled && setLoadError(toApiError(err)))
    return () => {
      cancelled = true
    }
  }, [status, user, technicianId])

  // Free times for the chosen day.
  useEffect(() => {
    if (!technician || !date) return
    let cancelled = false
    setAvailability(null)
    setSlotsError(null)
    setSlot(null)
    api
      .getAvailability(technician.id, date, bookingType)
      .then((a) => !cancelled && setAvailability(a))
      .catch((err) => !cancelled && setSlotsError(toApiError(err).message))
    return () => {
      cancelled = true
    }
  }, [technician, date, bookingType, slotsReload])

  // Any change to the form makes an earlier review out of date.
  useEffect(() => {
    setQuote(null)
    setAcknowledged(false)
  }, [bookingType, requestId, slot, useNext, area, address, note])

  const body = (): BookingInput => ({
    technician_id: technicianId,
    repair_request_id: requestId,
    booking_type: bookingType,
    ...(bookingType === 'expert_consultation' && useNext ? { next_available: true } : { scheduled_start: slot ?? undefined }),
    ...(bookingType === 'technician_visit' ? { service_area: area, service_address: address.trim() } : {}),
    ...(note.trim() ? { customer_note: note.trim() } : {}),
  })

  const localProblems = (): string | null => {
    if (!requestId) return 'Choose which repair request this is for.'
    if (!(bookingType === 'expert_consultation' && useNext) && !slot) return 'Choose a time.'
    if (bookingType === 'technician_visit') {
      if (!area) return 'Choose your area.'
      if (address.trim().length < 5) return 'Enter the address where the visit is needed (at least 5 characters).'
    }
    return null
  }
  const [localError, setLocalError] = useState<string | null>(null)

  const onReview = async (e: FormEvent) => {
    e.preventDefault()
    setFormError(null)
    const problem = localProblems()
    setLocalError(problem)
    if (problem) return
    setBusy('quote')
    try {
      setQuote(await api.quoteBooking(body()))
    } catch (err) {
      handleError(toApiError(err))
    } finally {
      setBusy(null)
    }
  }

  const handleError = useCallback((error: ApiError) => {
    setFormError(error)
    if (error.code === 'time_slot_unavailable' || error.code === 'invalid_time') {
      setQuote(null)
      setSlotsReload((n) => n + 1)
    }
  }, [])

  const onConfirm = async () => {
    if (!quote) return
    setBusy('confirm')
    setFormError(null)
    try {
      const booking = await api.createBooking({ ...body(), safety_acknowledged: quote.requires_safety_acknowledgement ? acknowledged : false })
      navigate(`${bookingUrl(booking.id)}?created=1`)
    } catch (err) {
      handleError(toApiError(err))
    } finally {
      setBusy(null)
    }
  }

  /* ---------- states before the form ---------- */

  if (status !== 'signedIn' || !user) {
    return (
      <PageContainer>
        <div className="flex items-center gap-3 text-navy-700" role="status">
          <Spinner /> Loading…
        </div>
      </PageContainer>
    )
  }

  const header = <PageHeader title={TYPE_TEXT[bookingType].title} documentTitle="Book" backFallback={ROUTES.technicians} />

  if (user.role !== 'customer') {
    return (
      <PageContainer>
        {header}
        <div className="mt-8 max-w-2xl">
          <Alert tone="info" title="Bookings are made from customer accounts">
            You’re signed in as a {user.role}. Sign in with a customer account to request a booking.
          </Alert>
        </div>
      </PageContainer>
    )
  }

  if (!technicianId || loadError) {
    return (
      <PageContainer>
        {header}
        <div className="mt-8 max-w-2xl">
          <Alert tone="error" title="This technician can’t be booked" action={<Button to={ROUTES.technicians}>Find a technician</Button>}>
            {loadError?.status === 404 ? 'They may not exist, may not be verified, or may no longer be listed.' : (loadError?.message ?? 'No technician was chosen.')}
          </Alert>
        </div>
      </PageContainer>
    )
  }

  if (!technician || !requests) {
    return (
      <PageContainer>
        {header}
        <div className="mt-10 flex items-center gap-3 text-navy-700" role="status">
          <Spinner /> Loading booking details…
        </div>
      </PageContainer>
    )
  }

  const trade = TRADES.find((t) => t.id === technician.trade)
  const price = bookingType === 'technician_visit' ? technician.visit_rate : technician.consultation_rate
  const today = new Date()
  const maxDate = localDateString(new Date(today.getTime() + 59 * 86_400_000))

  if (requests.length === 0) {
    return (
      <PageContainer>
        {header}
        <div className="mt-8 max-w-2xl">
          <Alert tone="info" title={`You don’t have a saved ${trade?.name.toLowerCase() ?? ''} request yet`} action={<Button to={ROUTES.diagnose}>Describe the problem</Button>}>
            A booking is always linked to one of your repair requests, so the technician knows what the problem is — and so the safety check
            has been done first.
          </Alert>
        </div>
      </PageContainer>
    )
  }

  const fieldError = (f: string) => formError?.fieldMessage(f)
  const selectClass =
    'mt-2 block h-12 w-full rounded-xl border border-navy-900/20 bg-white px-3 text-base text-navy-900 focus:border-teal-600 focus:outline-2 focus:outline-teal-600'

  return (
    <PageContainer>
      {header}

      <div className="mt-8 grid grid-cols-1 gap-8 lg:grid-cols-[1fr_20rem] lg:items-start">
        <form onSubmit={(e) => void onReview(e)} noValidate className="space-y-6" aria-label="Booking details">
          {/* Type */}
          {technician.offers_consultation && (
            <fieldset className="rounded-2xl border border-navy-900/10 bg-white p-5">
              <legend className="px-1 text-sm font-semibold text-navy-900">What do you need?</legend>
              <div className="mt-2 grid grid-cols-1 gap-3 sm:grid-cols-2">
                {(['technician_visit', 'expert_consultation'] as BookingType[]).map((t) => (
                  <label
                    key={t}
                    className={`flex cursor-pointer items-start gap-3 rounded-xl border p-4 ${bookingType === t ? 'border-teal-600 bg-teal-50' : 'border-navy-900/15'}`}
                  >
                    <input type="radio" name="type" checked={bookingType === t} onChange={() => setBookingType(t)} className="mt-1 accent-teal-700" />
                    <span>
                      <span className="block font-semibold text-navy-900">{TYPE_TEXT[t].short}</span>
                      <span className="block text-sm text-navy-600">
                        {money(t === 'technician_visit' ? technician.visit_rate : technician.consultation_rate, technician.currency)} listed rate
                      </span>
                    </span>
                  </label>
                ))}
              </div>
              {bookingType === 'expert_consultation' && (
                <p className="mt-3 flex items-start gap-2 text-sm text-navy-700">
                  <Icon name="info" className="mt-0.5 size-4 shrink-0" />
                  MENDORA doesn’t connect live audio or video calls yet. This books and tracks the consultation request only.
                </p>
              )}
            </fieldset>
          )}

          {/* Request */}
          <div className="rounded-2xl border border-navy-900/10 bg-white p-5">
            <label htmlFor="b-request" className="block text-sm font-semibold text-navy-900">
              Which problem is this for?
            </label>
            <select id="b-request" value={requestId} onChange={(e) => setRequestId(e.target.value)} className={selectClass}>
              {requests.map((r) => (
                <option key={r.request_id} value={r.request_id}>
                  {r.description.length > 70 ? `${r.description.slice(0, 70)}…` : r.description}
                  {r.safety.risk_level === 'high' ? ' (high risk)' : ''}
                </option>
              ))}
            </select>
            <p className="mt-2 text-xs text-navy-600">Only your {trade?.name.toLowerCase()} requests are listed, to match this technician’s trade.</p>
          </div>

          {/* Time */}
          <fieldset className="rounded-2xl border border-navy-900/10 bg-white p-5">
            <legend className="px-1 text-sm font-semibold text-navy-900">When?</legend>
            {bookingType === 'expert_consultation' && (
              <label className="mt-2 flex items-center gap-2 text-sm text-navy-800">
                <input type="checkbox" checked={useNext} onChange={(e) => setUseNext(e.target.checked)} className="size-4 accent-teal-700" />
                Book the next free slot (we’ll show you the time before you confirm)
              </label>
            )}
            {!(bookingType === 'expert_consultation' && useNext) && (
              <>
                <label htmlFor="b-date" className="mt-3 block text-sm text-navy-700">
                  Date
                </label>
                <input
                  id="b-date"
                  type="date"
                  value={date}
                  min={localDateString(today)}
                  max={maxDate}
                  onChange={(e) => setDate(e.target.value)}
                  className="mt-1 block h-12 w-full max-w-xs rounded-xl border border-navy-900/20 bg-white px-3 text-base text-navy-900 focus:border-teal-600 focus:outline-2 focus:outline-teal-600"
                />
                <div className="mt-4" aria-live="polite">
                  {slotsError ? (
                    <Alert tone="error" title="Free times couldn’t be loaded">
                      {slotsError}
                    </Alert>
                  ) : !availability ? (
                    <div className="flex items-center gap-2 text-sm text-navy-700" role="status">
                      <Spinner /> Checking free times…
                    </div>
                  ) : availability.slots.length === 0 ? (
                    <p className="text-sm text-navy-700">{availability.message ?? 'No free times on this day.'}</p>
                  ) : (
                    <>
                      <p className="text-sm text-navy-700">
                        Free start times ({availability.duration_minutes} minutes each, {availability.timezone} time):
                      </p>
                      <div className="mt-2 flex flex-wrap gap-2" role="radiogroup" aria-label="Start time">
                        {availability.slots.map((s) => (
                          <button
                            key={s.start}
                            type="button"
                            role="radio"
                            aria-checked={slot === s.start}
                            onClick={() => setSlot(s.start)}
                            className={`h-10 rounded-lg px-3 text-sm font-medium ring-1 ring-inset focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-600 ${
                              slot === s.start ? 'bg-teal-700 text-white ring-teal-700' : 'bg-white text-navy-900 ring-navy-900/15 hover:bg-navy-50'
                            }`}
                          >
                            {s.local_time}
                          </button>
                        ))}
                      </div>
                    </>
                  )}
                </div>
              </>
            )}
          </fieldset>

          {/* Place */}
          {bookingType === 'technician_visit' && (
            <div className="space-y-4 rounded-2xl border border-navy-900/10 bg-white p-5">
              <div>
                <label htmlFor="b-area" className="block text-sm font-semibold text-navy-900">
                  Your area
                </label>
                <select id="b-area" value={area} onChange={(e) => setArea(e.target.value)} className={selectClass}>
                  {technician.service_areas.map((a) => (
                    <option key={a} value={a}>
                      {a}
                    </option>
                  ))}
                </select>
                <p className="mt-1 text-xs text-navy-600">Only areas this technician covers. If yours isn’t listed, choose another technician.</p>
                {fieldError('service_area') && <p className="mt-1 text-sm text-red-700">{fieldError('service_area')}</p>}
              </div>
              <div>
                <label htmlFor="b-address" className="block text-sm font-semibold text-navy-900">
                  Address for the visit
                </label>
                <textarea
                  id="b-address"
                  value={address}
                  onChange={(e) => setAddress(e.target.value)}
                  maxLength={300}
                  rows={2}
                  className="mt-2 block w-full rounded-xl border border-navy-900/20 bg-white px-4 py-3 text-base text-navy-900 focus:border-teal-600 focus:outline-2 focus:outline-teal-600"
                />
                <p className="mt-1 flex items-start gap-1.5 text-xs text-navy-600">
                  <Icon name="lock" className="mt-px size-3.5 shrink-0" />
                  Shared with the technician only after they accept the booking.
                </p>
              </div>
            </div>
          )}

          <div className="rounded-2xl border border-navy-900/10 bg-white p-5">
            <label htmlFor="b-note" className="block text-sm font-semibold text-navy-900">
              Note for the technician <span className="font-normal text-navy-600">(optional)</span>
            </label>
            <textarea
              id="b-note"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              maxLength={500}
              rows={2}
              placeholder="e.g. access instructions"
              className="mt-2 block w-full rounded-xl border border-navy-900/20 bg-white px-4 py-3 text-base text-navy-900 placeholder:text-navy-600/70 focus:border-teal-600 focus:outline-2 focus:outline-teal-600"
            />
            <p className="mt-1 text-xs text-navy-600">Please don’t include phone numbers or other private details.</p>
          </div>

          {(localError || formError) && (
            <Alert tone="error" announce title={localError ? 'Please check the form' : 'The booking couldn’t be made'}>
              {localError ?? formError?.message}
              {formError?.details.length ? (
                <ul className="mt-1 list-disc pl-5">
                  {formError.details.map((d) => (
                    <li key={`${d.field}-${d.message}`}>{d.message}</li>
                  ))}
                </ul>
              ) : null}
            </Alert>
          )}

          {!quote && (
            <Button type="submit" size="lg" disabled={busy !== null}>
              {busy === 'quote' ? <Spinner /> : <Icon name="arrowRight" className="size-4" />}
              Review booking
            </Button>
          )}
        </form>

        {/* Summary / review */}
        <aside className="space-y-5 lg:sticky lg:top-24" aria-label="Booking summary">
          <div className="rounded-2xl border border-navy-900/10 bg-white p-5">
            <p className="font-semibold text-navy-900">{technician.display_name}</p>
            <p className="text-sm text-navy-600">{trade?.name}</p>
            <div className="mt-2 flex flex-wrap gap-2">
              <TechnicianBadges t={technician} />
            </div>
            <p className="mt-3 text-sm text-navy-700">
              Listed rate: <span className="font-semibold text-navy-900">{money(price, technician.currency)}</span>
            </p>
            <Button to={techniciansUrl({ trade: technician.trade, request: requestId || undefined })} variant="secondary" className="mt-4 w-full">
              Choose a different technician
            </Button>
          </div>

          {quote && (
            <section aria-labelledby="review-heading" className="rounded-2xl border-2 border-teal-600 bg-white p-5" aria-live="polite">
              <h2 id="review-heading" className="font-semibold text-navy-900">
                Review and confirm
              </h2>
              <dl className="mt-3 space-y-2 text-sm">
                <div>
                  <dt className="text-navy-600">What</dt>
                  <dd className="font-medium text-navy-900">{TYPE_TEXT[quote.booking_type].short}</dd>
                </div>
                <div>
                  <dt className="text-navy-600">When</dt>
                  <dd className="font-medium text-navy-900">{quote.local_time_label}</dd>
                </div>
                <div>
                  <dt className="text-navy-600">Price</dt>
                  <dd className="font-medium text-navy-900">{money(quote.price_amount, quote.price_currency)}</dd>
                </div>
              </dl>
              <ul className="mt-3 space-y-1 text-xs text-navy-700">
                {quote.notes.map((n) => (
                  <li key={n} className="flex items-start gap-1.5">
                    <Icon name="info" className="mt-px size-3.5 shrink-0" />
                    {n}
                  </li>
                ))}
              </ul>

              {quote.requires_safety_acknowledgement && (
                <div className="mt-4 rounded-xl border border-red-700/20 bg-red-50 p-4 text-sm text-red-900">
                  <p className="flex items-center gap-2 font-semibold">
                    <Icon name="alert" className="size-4" /> This request is high risk
                  </p>
                  <p className="mt-1">{quote.safety_message}</p>
                  {quote.emergency_steps.length > 0 && (
                    <ul className="mt-2 list-disc space-y-0.5 pl-5">
                      {quote.emergency_steps.map((s) => (
                        <li key={s}>{s}</li>
                      ))}
                    </ul>
                  )}
                  <label className="mt-3 flex items-start gap-2 font-medium">
                    <input type="checkbox" checked={acknowledged} onChange={(e) => setAcknowledged(e.target.checked)} className="mt-1 size-4 accent-red-700" />
                    I am safe right now, and I understand MENDORA is not an emergency service.
                  </label>
                </div>
              )}

              <div className="mt-4 flex flex-col gap-2">
                <Button
                  onClick={() => void onConfirm()}
                  disabled={busy !== null || (quote.requires_safety_acknowledgement && !acknowledged)}
                >
                  {busy === 'confirm' ? <Spinner /> : <Icon name="check" className="size-4" />}
                  Confirm booking request
                </Button>
                <Button variant="secondary" onClick={() => setQuote(null)} disabled={busy !== null}>
                  Change details
                </Button>
              </div>
            </section>
          )}

          {technician.is_sample && (
            <Badge tone="amber" icon="info">
              Nobody will respond to a demo sample
            </Badge>
          )}
        </aside>
      </div>
    </PageContainer>
  )
}
