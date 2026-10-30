import { useEffect, useState, type FormEvent } from 'react'
import PageHeader, { PageContainer } from '../components/PageHeader'
import Alert from '../components/Alert'
import Badge from '../components/Badge'
import Button from '../components/Button'
import Icon from '../components/Icon'
import Spinner from '../components/Spinner'
import PaymentPanel from '../components/payments/PaymentPanel'
import EstimatePanel from '../components/bookings/EstimatePanel'
import ReviewPanel from '../components/bookings/ReviewPanel'
import RequestPhotos from '../components/photos/RequestPhotos'
import { useRouter } from '../lib/router'
import { ApiError, api, type Booking, type BookingAction } from '../lib/api'
import { ROUTES, bookingUrl, loginUrl, requestUrl } from '../data/content'
import { useAuth } from '../state/AuthContext'
import { formatDate } from './RequestPage'
import { STATUS_BADGE, TYPE_LABEL } from './BookingsPage'
import { money } from './TechniciansPage'

/*
  One booking (URL: /bookings/<id>): details, status history and the actions YOU may take.
  The server decides which actions are allowed (booking.allowed_actions) and checks them again.
*/

const ACTION_TEXT: Record<BookingAction, { button: string; done: string }> = {
  accept: { button: 'Accept booking', done: 'Booking accepted. The customer has been notified in MENDORA.' },
  reject: { button: 'Decline', done: 'Booking declined. The customer has been notified in MENDORA.' },
  cancel: { button: 'Cancel booking', done: 'Booking cancelled. The other person has been notified in MENDORA.' },
  complete: { button: 'Mark as completed', done: 'Marked as completed.' },
}

function toApiError(err: unknown): ApiError {
  return err instanceof ApiError ? err : new ApiError(0, 'unknown', 'Something went wrong. Please try again.')
}

export default function BookingDetailPage({ bookingId }: { bookingId: string }) {
  const { status, user } = useAuth()
  const { location, replace } = useRouter()
  const [booking, setBooking] = useState<Booking | null>(null)
  const [loadError, setLoadError] = useState<ApiError | null>(null)
  const [pending, setPending] = useState<BookingAction | null>(null) // action with an open form
  const [reason, setReason] = useState('')
  const [cause, setCause] = useState('')
  const [parts, setParts] = useState('')
  const [minutes, setMinutes] = useState('')
  const [busy, setBusy] = useState(false)
  const [actionError, setActionError] = useState<ApiError | null>(null)
  const [success, setSuccess] = useState<string | null>(
    new URLSearchParams(location.search).get('created') ? 'Booking request sent. You’ll see updates here and under Bookings.' : null,
  )

  useEffect(() => {
    if (status === 'signedOut') replace(loginUrl(bookingUrl(bookingId)))
  }, [status, replace, bookingId])

  useEffect(() => {
    if (status !== 'signedIn') return
    let cancelled = false
    api
      .getBooking(bookingId)
      .then((b) => !cancelled && setBooking(b))
      .catch((err) => !cancelled && setLoadError(toApiError(err)))
    // Opening a booking marks its notifications as read.
    api
      .listNotifications()
      .then(async (n) => {
        const unread = n.notifications.filter((x) => x.booking_id === bookingId && !x.read)
        await Promise.all(unread.map((x) => api.markNotificationRead(x.id)))
        if (unread.length) window.dispatchEvent(new Event('mendora:notifications'))
      })
      .catch(() => undefined)
    return () => {
      cancelled = true
    }
  }, [status, bookingId])

  const run = async (action: BookingAction) => {
    if (!booking) return
    setBusy(true)
    setActionError(null)
    setSuccess(null)
    let body: object | undefined
    if (action === 'reject' || action === 'cancel') body = reason.trim() ? { reason: reason.trim() } : undefined
    if (action === 'complete') {
      const report: Record<string, unknown> = {}
      if (cause.trim()) report.confirmed_cause = cause.trim()
      const partList = parts.split(',').map((p) => p.trim()).filter(Boolean)
      if (partList.length) report.parts_used = partList
      if (minutes.trim()) report.completion_minutes = Number(minutes)
      body = Object.keys(report).length ? report : undefined
    }
    try {
      setBooking(await api.bookingAction(booking.id, action, body))
      setSuccess(ACTION_TEXT[action].done)
      setPending(null)
      setReason('')
    } catch (err) {
      const e = toApiError(err)
      setActionError(e)
      // The booking may have changed elsewhere: show its current state.
      api.getBooking(booking.id).then(setBooking).catch(() => undefined)
    } finally {
      setBusy(false)
    }
  }

  const onSubmitForm = (e: FormEvent) => {
    e.preventDefault()
    if (pending) void run(pending)
  }

  if (loadError) {
    return (
      <PageContainer>
        <PageHeader title="Booking" documentTitle="Booking" backFallback={ROUTES.bookings} />
        <div className="mt-8 max-w-2xl">
          <Alert tone="error" title={loadError.status === 404 ? 'We couldn’t find this booking' : 'This booking couldn’t be loaded'} action={<Button to={ROUTES.bookings}>All bookings</Button>}>
            {loadError.status === 404 ? 'It may not exist, or it may belong to someone else.' : loadError.message}
          </Alert>
        </div>
      </PageContainer>
    )
  }

  if (!booking) {
    return (
      <PageContainer>
        <PageHeader title="Booking" documentTitle="Booking" backFallback={ROUTES.bookings} />
        <div className="mt-10 flex items-center gap-3 text-navy-700" role="status">
          <Spinner /> Loading booking…
        </div>
      </PageContainer>
    )
  }

  const badge = STATUS_BADGE[booking.status]
  const actions = booking.allowed_actions
  const inputClass =
    'mt-1 block w-full rounded-xl border border-navy-900/20 bg-white px-3 py-2 text-base text-navy-900 focus:border-teal-600 focus:outline-2 focus:outline-teal-600'

  return (
    <PageContainer>
      <PageHeader
        title={TYPE_LABEL[booking.booking_type]}
        documentTitle="Booking"
        backFallback={ROUTES.bookings}
        aside={<Badge tone={badge.tone}>{badge.label}</Badge>}
        intro={booking.local_time_label}
      />

      <div className="mt-8 grid grid-cols-1 gap-8 lg:grid-cols-[1fr_20rem] lg:items-start">
        <div className="space-y-6">
          {success && (
            <Alert tone="success" announce title={success} />
          )}
          {booking.technician.is_sample && (
            <Alert tone="warning" title="Demo sample technician">
              {booking.technician.sample_notice ?? 'This is a made-up test record.'} Nobody will actually visit or respond unless you sign in as the sample account.
            </Alert>
          )}

          <section className="rounded-2xl border border-navy-900/10 bg-white p-5 sm:p-6" aria-labelledby="details-heading">
            <h2 id="details-heading" className="font-semibold text-navy-900">
              Details
            </h2>
            <dl className="mt-4 grid grid-cols-1 gap-4 text-sm sm:grid-cols-2">
              <div>
                <dt className="text-navy-600">Technician</dt>
                <dd className="font-medium text-navy-900">{booking.technician.display_name}</dd>
                <dd className="text-xs text-navy-600">{booking.technician.verification_label}</dd>
              </div>
              <div>
                <dt className="text-navy-600">Customer</dt>
                <dd className="font-medium text-navy-900">{booking.customer_display_name}</dd>
              </div>
              <div>
                <dt className="text-navy-600">When</dt>
                <dd className="font-medium text-navy-900">{booking.local_time_label}</dd>
              </div>
              <div>
                <dt className="text-navy-600">Price (listed rate)</dt>
                <dd className="font-medium text-navy-900">{money(booking.price_amount, booking.price_currency)}</dd>
                <dd className="text-xs text-navy-600">{booking.price_note}</dd>
              </div>
              {booking.booking_type === 'technician_visit' && (
                <>
                  <div>
                    <dt className="text-navy-600">Area</dt>
                    <dd className="font-medium text-navy-900">{booking.service_area}</dd>
                  </div>
                  <div>
                    <dt className="text-navy-600">Address</dt>
                    <dd className="font-medium break-words text-navy-900">
                      {booking.service_address ?? <span className="flex items-center gap-1.5 font-normal text-navy-600"><Icon name="lock" className="size-3.5" /> {booking.address_note}</span>}
                    </dd>
                  </div>
                </>
              )}
              {booking.customer_note && (
                <div className="sm:col-span-2">
                  <dt className="text-navy-600">Note</dt>
                  <dd className="break-words text-navy-900">{booking.customer_note}</dd>
                </div>
              )}
            </dl>
            {booking.consultation_note && (
              <p className="mt-4 flex items-start gap-2 rounded-lg bg-navy-50 p-3 text-sm text-navy-800">
                <Icon name="info" className="mt-0.5 size-4 shrink-0" />
                {booking.consultation_note}
              </p>
            )}
          </section>

          {user?.role === 'customer' && (
            <ReviewPanel booking={booking} onReviewed={() => void api.getBooking(booking.id).then(setBooking).catch(() => undefined)} />
          )}

          <EstimatePanel booking={booking} onUpdated={setBooking} />

          <section className="rounded-2xl border border-navy-900/10 bg-white p-5 sm:p-6" aria-labelledby="problem-heading">
            <h2 id="problem-heading" className="flex flex-wrap items-center gap-2 font-semibold text-navy-900">
              The problem
              {booking.safety_risk_level === 'high' && (
                <Badge tone="red" icon="alert">
                  High risk
                </Badge>
              )}
            </h2>
            <p className="mt-3 text-sm leading-relaxed break-words whitespace-pre-wrap text-navy-800">{booking.repair_request.description}</p>
            {booking.safety_risk_level === 'high' && (
              <p className="mt-3 text-sm text-red-900">
                The customer’s safety check found a possible danger. Follow safe working practice; the customer confirmed they were safe when booking.
              </p>
            )}
          </section>

          {(booking.status === 'accepted' || booking.status === 'completed' || user?.role !== 'technician') && (
            <RequestPhotos requestId={booking.repair_request.id} canEdit={user?.role === 'customer'} />
          )}

          <section className="rounded-2xl border border-navy-900/10 bg-white p-5 sm:p-6" aria-labelledby="history-heading">
            <h2 id="history-heading" className="font-semibold text-navy-900">
              Status history
            </h2>
            <ol className="mt-4 space-y-3 border-l-2 border-navy-900/10 pl-4">
              {booking.history.map((h, i) => (
                <li key={`${h.status}-${i}`} className="relative text-sm">
                  <span className="absolute top-1.5 -left-[1.4rem] size-2.5 rounded-full bg-teal-600" aria-hidden="true" />
                  <span className="font-medium text-navy-900">{STATUS_BADGE[h.status].label}</span>
                  <span className="text-navy-600"> · by {h.by} · {formatDate(h.at)}</span>
                  {h.reason && <span className="block text-navy-700">“{h.reason}”</span>}
                </li>
              ))}
            </ol>
          </section>
        </div>

        <aside className="space-y-5" aria-label="Payment and actions">
          {booking.booking_type && (
            <PaymentPanel
              booking={booking}
              showHistory={user?.role !== 'technician'}
              onChanged={() => void api.getBooking(booking.id).then(setBooking).catch(() => undefined)}
            />
          )}
          <div className="rounded-2xl border border-navy-900/10 bg-white p-5">
            <h2 className="font-semibold text-navy-900">What you can do</h2>
            {actionError && (
              <div className="mt-3">
                <Alert tone="error" announce title="That didn’t work">
                  {actionError.message}
                </Alert>
              </div>
            )}
            {actions.length === 0 ? (
              <p className="mt-3 text-sm text-navy-600">
                {booking.status === 'requested' || booking.status === 'accepted'
                  ? 'Nothing to do right now.'
                  : 'This booking is closed. No further changes can be made.'}
              </p>
            ) : pending ? (
              <form onSubmit={onSubmitForm} className="mt-3 space-y-3">
                {(pending === 'reject' || pending === 'cancel') && (
                  <div>
                    <label htmlFor="a-reason" className="block text-sm font-medium text-navy-900">
                      Reason <span className="font-normal text-navy-600">(optional, shared with the other person)</span>
                    </label>
                    <input id="a-reason" value={reason} onChange={(e) => setReason(e.target.value)} maxLength={300} className={inputClass} />
                  </div>
                )}
                {pending === 'complete' && (
                  <>
                    <p className="text-xs text-navy-600">
                      Optional. What you confirm is saved as an <strong>unverified</strong> repair record until an admin checks it.
                    </p>
                    <div>
                      <label htmlFor="a-cause" className="block text-sm font-medium text-navy-900">
                        Confirmed cause
                      </label>
                      <input id="a-cause" value={cause} onChange={(e) => setCause(e.target.value)} maxLength={500} className={inputClass} />
                    </div>
                    <div>
                      <label htmlFor="a-parts" className="block text-sm font-medium text-navy-900">
                        Parts used (comma-separated)
                      </label>
                      <input id="a-parts" value={parts} onChange={(e) => setParts(e.target.value)} className={inputClass} />
                    </div>
                    <div>
                      <label htmlFor="a-mins" className="block text-sm font-medium text-navy-900">
                        Time taken (minutes)
                      </label>
                      <input id="a-mins" type="number" min={1} max={1440} value={minutes} onChange={(e) => setMinutes(e.target.value)} className={inputClass} />
                    </div>
                  </>
                )}
                <p className="text-sm text-navy-800">Are you sure you want to {pending === 'complete' ? 'mark this as completed' : `${pending} this booking`}?</p>
                <div className="flex flex-col gap-2">
                  <Button type="submit" disabled={busy}>
                    {busy && <Spinner />}
                    Yes, {ACTION_TEXT[pending].button.toLowerCase()}
                  </Button>
                  <Button variant="secondary" onClick={() => setPending(null)} disabled={busy}>
                    Go back
                  </Button>
                </div>
              </form>
            ) : (
              <div className="mt-3 flex flex-col gap-2">
                {actions.includes('accept') && (
                  <Button onClick={() => void run('accept')} disabled={busy}>
                    {busy ? <Spinner /> : <Icon name="check" className="size-4" />}
                    {ACTION_TEXT.accept.button}
                  </Button>
                )}
                {actions.includes('complete') && <Button onClick={() => setPending('complete')}>{ACTION_TEXT.complete.button}</Button>}
                {actions.includes('reject') && (
                  <Button variant="secondary" onClick={() => setPending('reject')}>
                    {ACTION_TEXT.reject.button}
                  </Button>
                )}
                {actions.includes('cancel') && (
                  <Button variant="secondary" onClick={() => setPending('cancel')}>
                    {ACTION_TEXT.cancel.button}
                  </Button>
                )}
              </div>
            )}
            <p className="mt-4 text-xs leading-relaxed text-navy-600">Updates are shown inside MENDORA only. No email or SMS is sent.</p>
          </div>
          <div className="flex flex-col gap-2">
            <Button to={ROUTES.bookings} variant="secondary">
              All bookings
            </Button>
            {user?.role !== 'technician' && (
              <Button to={requestUrl(booking.repair_request.id)} variant="secondary">
                View repair request
              </Button>
            )}
          </div>
        </aside>
      </div>
    </PageContainer>
  )
}
