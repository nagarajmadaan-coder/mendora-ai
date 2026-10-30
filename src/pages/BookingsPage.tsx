import { useCallback, useEffect, useState } from 'react'
import PageHeader, { PageContainer } from '../components/PageHeader'
import Alert from '../components/Alert'
import Badge from '../components/Badge'
import Button from '../components/Button'
import Icon from '../components/Icon'
import Spinner from '../components/Spinner'
import { Link, useRouter } from '../lib/router'
import { ApiError, api, type Booking, type BookingStatus, type NotificationList } from '../lib/api'
import { ROUTES, bookingUrl, loginUrl } from '../data/content'
import { useAuth } from '../state/AuthContext'
import { formatDate } from './RequestPage'
import { money } from './TechniciansPage'

/*
  Bookings (URL: /bookings).
  - Customers see their own bookings; technicians see bookings assigned to them; admins see all.
  - In-app notifications are listed beside them. Nothing is emailed or texted.
*/

export const STATUS_BADGE: Record<BookingStatus, { label: string; tone: 'teal' | 'amber' | 'navy' | 'red' }> = {
  requested: { label: 'Waiting for technician', tone: 'amber' },
  accepted: { label: 'Accepted', tone: 'teal' },
  rejected: { label: 'Declined', tone: 'red' },
  cancelled: { label: 'Cancelled', tone: 'navy' },
  completed: { label: 'Completed', tone: 'teal' },
}

export const TYPE_LABEL = { technician_visit: 'Technician visit', expert_consultation: 'Expert consultation' } as const

const FILTERS: { label: string; value: BookingStatus | '' }[] = [
  { label: 'All', value: '' },
  { label: 'Waiting', value: 'requested' },
  { label: 'Accepted', value: 'accepted' },
  { label: 'Completed', value: 'completed' },
  { label: 'Cancelled', value: 'cancelled' },
  { label: 'Declined', value: 'rejected' },
]

export default function BookingsPage() {
  const { status, user } = useAuth()
  const { replace } = useRouter()
  const [filter, setFilter] = useState<BookingStatus | ''>('')
  const [bookings, setBookings] = useState<Booking[] | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [notes, setNotes] = useState<NotificationList | null>(null)
  const [reload, setReload] = useState(0)

  useEffect(() => {
    if (status === 'signedOut') replace(loginUrl(ROUTES.bookings))
  }, [status, replace])

  useEffect(() => {
    if (status !== 'signedIn') return
    let cancelled = false
    setBookings(null)
    setError(null)
    api
      .listBookings(filter || undefined)
      .then((r) => !cancelled && setBookings(r.bookings))
      .catch((err) => !cancelled && setError(err instanceof ApiError ? err : new ApiError(0, 'unknown', 'Something went wrong.')))
    api
      .listNotifications()
      .then((n) => !cancelled && setNotes(n))
      .catch(() => undefined)
    return () => {
      cancelled = true
    }
  }, [status, filter, reload])

  const markAll = useCallback(async () => {
    try {
      setNotes(await api.markAllNotificationsRead())
      window.dispatchEvent(new Event('mendora:notifications'))
    } catch {
      /* the list stays as it is */
    }
  }, [])

  if (status !== 'signedIn' || !user) {
    return (
      <PageContainer>
        <div className="flex items-center gap-3 text-navy-700" role="status">
          <Spinner /> Loading…
        </div>
      </PageContainer>
    )
  }

  const isTech = user.role === 'technician'

  return (
    <PageContainer>
      <PageHeader
        title={isTech ? 'Assigned bookings' : user.role === 'admin' ? 'All bookings' : 'My bookings'}
        documentTitle="Bookings"
        intro={
          isTech
            ? 'Requests from customers. Accept or decline each one. The customer’s address is shown only after you accept.'
            : 'Your technician visits and expert consultations. Payments are a sandbox demonstration — no real money is taken.'
        }
      />

      <div className="mt-8 grid grid-cols-1 gap-8 lg:grid-cols-[1fr_20rem] lg:items-start">
        <section aria-label="Bookings">
          <div className="flex flex-wrap gap-2" role="group" aria-label="Filter by status">
            {FILTERS.map((f) => (
              <button
                key={f.label}
                type="button"
                aria-pressed={filter === f.value}
                onClick={() => setFilter(f.value)}
                className={`h-9 rounded-full px-4 text-sm font-medium ring-1 ring-inset focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-600 ${
                  filter === f.value ? 'bg-navy-900 text-white ring-navy-900' : 'bg-white text-navy-800 ring-navy-900/15 hover:bg-navy-50'
                }`}
              >
                {f.label}
              </button>
            ))}
          </div>

          <div className="mt-5" aria-live="polite">
            {error ? (
              <Alert tone="error" announce title="Bookings couldn’t be loaded" action={<Button variant="secondary" onClick={() => setReload((n) => n + 1)}>Try again</Button>}>
                {error.message}
              </Alert>
            ) : bookings === null ? (
              <div className="flex items-center gap-3 rounded-2xl border border-navy-900/10 bg-white p-6 text-navy-700" role="status">
                <Spinner /> Loading bookings…
              </div>
            ) : bookings.length === 0 ? (
              <div className="rounded-2xl border border-dashed border-navy-900/20 bg-white p-8 text-center">
                <Icon name="calendar" className="mx-auto size-8 text-navy-600" />
                <p className="mt-3 font-semibold text-navy-900">{filter ? 'No bookings with this status' : 'No bookings yet'}</p>
                <p className="mt-1 text-sm text-navy-600">
                  {isTech ? 'New requests will appear here.' : 'Find a technician from one of your repair requests.'}
                </p>
                {!isTech && !filter && (
                  <div className="mt-5">
                    <Button to={ROUTES.technicians}>Find a technician</Button>
                  </div>
                )}
              </div>
            ) : (
              <ul className="space-y-3">
                {bookings.map((b) => {
                  const badge = STATUS_BADGE[b.status]
                  const needsResponse = isTech && b.allowed_actions.includes('accept')
                  return (
                    <li key={b.id}>
                      <Link
                        to={bookingUrl(b.id)}
                        className="group flex items-start gap-4 rounded-2xl border border-navy-900/10 bg-white p-4 transition-colors hover:border-teal-600/50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-600 sm:p-5"
                      >
                        <span className="flex size-11 shrink-0 items-center justify-center rounded-lg bg-navy-900 text-teal-300">
                          <Icon name={b.booking_type === 'technician_visit' ? 'mapPin' : 'message'} className="size-5" />
                        </span>
                        <span className="min-w-0 flex-1">
                          <span className="flex flex-wrap items-center gap-2">
                            <span className="font-semibold text-navy-900">{TYPE_LABEL[b.booking_type]}</span>
                            <Badge tone={badge.tone}>{badge.label}</Badge>
                            {needsResponse && <Badge tone="amber" icon="bell">Needs your response</Badge>}
                            {b.safety_risk_level === 'high' && <Badge tone="red" icon="alert">High risk</Badge>}
                            {b.technician.is_sample && <Badge tone="amber">Demo sample</Badge>}
                            {b.payment.status === 'paid' && <Badge tone="teal" icon="check">Paid (sandbox)</Badge>}
                            {b.payment.status === 'refunded' && <Badge tone="navy">Refunded (sandbox)</Badge>}
                            {b.payment.can_pay && <Badge tone="amber">Payment due</Badge>}
                          </span>
                          <span className="mt-1 block text-sm text-navy-800">{b.local_time_label}</span>
                          <span className="mt-0.5 block text-sm text-navy-600">
                            {isTech ? `Customer: ${b.customer_display_name}` : b.technician.display_name} · {money(b.price_amount, b.price_currency)}
                          </span>
                        </span>
                        <Icon name="arrowRight" className="mt-1 size-5 shrink-0 text-navy-600 group-hover:text-teal-700" />
                      </Link>
                    </li>
                  )
                })}
              </ul>
            )}
          </div>
        </section>

        <aside className="rounded-2xl border border-navy-900/10 bg-white p-5" aria-labelledby="notes-heading">
          <div className="flex items-center justify-between gap-2">
            <h2 id="notes-heading" className="flex items-center gap-2 font-semibold text-navy-900">
              <Icon name="bell" className="size-4" /> Notifications
              {notes && notes.unread_count > 0 && <Badge tone="teal">{notes.unread_count} new</Badge>}
            </h2>
            {notes && notes.unread_count > 0 && (
              <button type="button" onClick={() => void markAll()} className="text-sm font-medium text-teal-800 hover:underline">
                Mark all read
              </button>
            )}
          </div>
          {!notes ? (
            <p className="mt-3 text-sm text-navy-600">Loading…</p>
          ) : notes.notifications.length === 0 ? (
            <p className="mt-3 text-sm text-navy-600">No notifications yet.</p>
          ) : (
            <ul className="mt-3 max-h-[28rem] space-y-2 overflow-y-auto">
              {notes.notifications.map((n) => (
                <li key={n.id} className={`rounded-lg p-3 text-sm ${n.read ? 'bg-white text-navy-700 ring-1 ring-inset ring-navy-900/10' : 'bg-teal-50 text-navy-900'}`}>
                  {n.booking_id ? (
                    <Link to={bookingUrl(n.booking_id)} className="hover:underline">
                      {n.message}
                    </Link>
                  ) : (
                    n.message
                  )}
                  <span className="mt-1 block text-xs text-navy-600">{formatDate(n.created_at)}</span>
                </li>
              ))}
            </ul>
          )}
          <p className="mt-4 text-xs leading-relaxed text-navy-600">{notes?.note ?? 'Updates appear inside MENDORA only.'}</p>
        </aside>
      </div>
    </PageContainer>
  )
}
