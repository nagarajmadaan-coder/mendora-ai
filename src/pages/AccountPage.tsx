import { useEffect, useState } from 'react'
import PageHeader, { PageContainer } from '../components/PageHeader'
import Alert from '../components/Alert'
import Badge from '../components/Badge'
import Button from '../components/Button'
import Icon from '../components/Icon'
import Spinner from '../components/Spinner'
import { Link, useRouter } from '../lib/router'
import { ApiError, api, type RepairRequest } from '../lib/api'
import { ROUTES, TRADES, loginUrl, requestUrl } from '../data/content'
import { useAuth } from '../state/AuthContext'
import { formatDate } from './RequestPage'

/* "My requests" (URL: /account) — the signed-in user's profile and private request history. */

function StatusBadge({ request }: { request: RepairRequest }) {
  if (request.safety.risk_level === 'high')
    return (
      <Badge tone="red" icon="alert">
        High risk — safety advice
      </Badge>
    )
  if (request.diagnosis_status === 'completed')
    return (
      <Badge tone="teal" icon="checkCircle">
        AI assessed
      </Badge>
    )
  if (request.safety.risk_level === 'medium')
    return (
      <Badge tone="amber" icon="shield">
        Safety check needed
      </Badge>
    )
  if (request.diagnosis_status === 'failed') return <Badge tone="amber">Diagnosis not available</Badge>
  return <Badge tone="navy">Not diagnosed</Badge>
}

export default function AccountPage() {
  const { status, user, logout } = useAuth()
  const { replace, navigate } = useRouter()
  const [items, setItems] = useState<RepairRequest[] | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [reload, setReload] = useState(0)

  // Signed out → go to sign in, then come back here.
  useEffect(() => {
    if (status === 'signedOut') replace(loginUrl(ROUTES.account, 'account'))
  }, [status, replace])

  useEffect(() => {
    if (status !== 'signedIn' || user?.role !== 'customer') return
    let cancelled = false
    setError(null)
    setItems(null)
    api
      .listMyRepairRequests()
      .then((res) => !cancelled && setItems(res.items))
      .catch((err) => !cancelled && setError(err instanceof ApiError ? err : new ApiError(0, 'unknown', 'Something went wrong.')))
    return () => {
      cancelled = true
    }
  }, [status, user, reload])

  if (status !== 'signedIn' || !user) {
    return (
      <PageContainer>
        <div className="flex items-center gap-3 text-navy-700" role="status">
          <Spinner /> Loading your account…
        </div>
      </PageContainer>
    )
  }

  return (
    <PageContainer>
      <PageHeader title="My requests" documentTitle="My requests" intro={`Signed in as ${user.full_name}.`} />

      <div className="mt-8 grid grid-cols-1 gap-8 lg:grid-cols-[1fr_20rem] lg:items-start">
        <section aria-labelledby="history-heading">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 id="history-heading" className="text-xl font-semibold text-navy-900">
              Repair history
            </h2>
            {user.role === 'customer' && <Button to={ROUTES.diagnose}>New request</Button>}
          </div>

          <div className="mt-5">
            {user.role !== 'customer' ? (
              <Alert
                tone="info"
                title={user.role === 'admin' ? 'Admin account' : 'Technician account'}
                action={
                  <div className="flex flex-wrap gap-3">
                    {user.role === 'technician' && <Button to={ROUTES.technicianProfile}>My technician profile</Button>}
                    {user.role === 'admin' && <Button to={ROUTES.admin}>Admin dashboard</Button>}
                    <Button to={ROUTES.bookings} variant="secondary">
                      {user.role === 'technician' ? 'Assigned bookings' : 'All bookings'}
                    </Button>
                  </div>
                }
              >
                {user.role === 'admin'
                  ? 'Use the admin dashboard to verify technicians and repair cases and to see high-risk reports. Creating staff accounts is still done from the command line or /docs.'
                  : 'Set up your profile and ask an admin to verify it. Once verified, customers can book you and their requests appear under Assigned bookings.'}
              </Alert>
            ) : error ? (
              <Alert tone="error" announce title="Your requests couldn’t be loaded" action={<Button variant="secondary" onClick={() => setReload((n) => n + 1)}>Try again</Button>}>
                {error.message}
              </Alert>
            ) : items === null ? (
              <div className="flex items-center gap-3 rounded-2xl border border-navy-900/10 bg-white p-6 text-navy-700" role="status">
                <Spinner /> Loading your requests…
              </div>
            ) : items.length === 0 ? (
              <div className="rounded-2xl border border-dashed border-navy-900/20 bg-white p-8 text-center">
                <Icon name="message" className="mx-auto size-8 text-navy-600" />
                <p className="mt-3 font-semibold text-navy-900">No repair requests yet</p>
                <p className="mt-1 text-sm text-navy-600">Describe a problem to get started.</p>
                <div className="mt-5">
                  <Button to={ROUTES.diagnose}>Diagnose a Problem</Button>
                </div>
              </div>
            ) : (
              <ul className="space-y-3">
                {items.map((item) => {
                  const trade = TRADES.find((t) => t.id === item.trade.id)
                  return (
                    <li key={item.request_id}>
                      <Link
                        to={requestUrl(item.request_id)}
                        className="group flex items-start gap-4 rounded-2xl border border-navy-900/10 bg-white p-4 transition-colors hover:border-teal-600/50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-600 sm:p-5"
                      >
                        <span className="flex size-11 shrink-0 items-center justify-center rounded-lg bg-navy-900 text-teal-300">
                          <Icon name={trade?.icon ?? 'home'} className="size-5" />
                        </span>
                        <span className="min-w-0 flex-1">
                          <span className="flex flex-wrap items-center gap-2">
                            <span className="font-semibold text-navy-900">{item.trade.name}</span>
                            <StatusBadge request={item} />
                          </span>
                          <span className="mt-1 block line-clamp-2 text-sm break-words text-navy-700">{item.description}</span>
                          <span className="mt-1 block text-xs text-navy-600">{formatDate(item.created_at)}</span>
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

        <aside className="rounded-2xl border border-navy-900/10 bg-white p-5" aria-label="Your account">
          <h2 className="font-semibold text-navy-900">Your account</h2>
          <dl className="mt-4 space-y-3 text-sm">
            <div>
              <dt className="text-navy-600">Name</dt>
              <dd className="font-medium text-navy-900">{user.full_name}</dd>
            </div>
            <div>
              <dt className="text-navy-600">Email</dt>
              <dd className="font-medium break-all text-navy-900">{user.email}</dd>
            </div>
            <div>
              <dt className="text-navy-600">Account type</dt>
              <dd className="mt-1">
                <Badge tone={user.role === 'customer' ? 'navy' : 'teal'}>{user.role[0].toUpperCase() + user.role.slice(1)}</Badge>
              </dd>
            </div>
          </dl>
          <p className="mt-4 flex items-start gap-2 text-xs leading-relaxed text-navy-600">
            <Icon name="lock" className="mt-px size-3.5 shrink-0" />
            Your requests are private: other customers can’t see them.
          </p>
          <Button
            variant="secondary"
            className="mt-5 w-full"
            onClick={() => {
              logout()
              navigate(ROUTES.home)
            }}
          >
            Sign out
          </Button>
        </aside>
      </div>
    </PageContainer>
  )
}
