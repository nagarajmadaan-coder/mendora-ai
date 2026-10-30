import { useCallback, useEffect, useState } from 'react'
import PageHeader, { PageContainer } from '../components/PageHeader'
import Alert from '../components/Alert'
import Badge from '../components/Badge'
import Button from '../components/Button'
import Spinner from '../components/Spinner'
import { Link, useRouter } from '../lib/router'
import { ApiError, api, type AdminStats, type AdminTechnician, type RepairCase, type SafetyEscalation } from '../lib/api'
import { ROUTES, loginUrl, requestUrl } from '../data/content'
import { useAuth } from '../state/AuthContext'
import { formatDate } from './RequestPage'

/*
  Admin dashboard (URL: /admin) — merged feature. Admin accounts only (the server checks every call).
  Verifying a technician or a repair case needs a written note of what was actually checked.
*/

function Stat({ label, value, hint }: { label: string; value: string | number; hint?: string }) {
  return (
    <div className="rounded-xl border border-navy-900/10 bg-white p-4">
      <p className="text-xs font-semibold tracking-wide text-navy-600 uppercase">{label}</p>
      <p className="mt-1 text-2xl font-bold text-navy-900">{value}</p>
      {hint && <p className="mt-0.5 text-xs text-navy-600">{hint}</p>}
    </div>
  )
}

const sum = (o: Record<string, number>) => Object.values(o).reduce((a, b) => a + b, 0)

function DecisionForm({ placeholder, minLength, rejectMin = 5, onSubmit }: { placeholder: string; minLength: number; rejectMin?: number; onSubmit: (text: string, approve: boolean) => Promise<void> }) {
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const short = text.trim().length < minLength
  const go = async (approve: boolean) => {
    setBusy(true)
    try {
      await onSubmit(text.trim(), approve)
      setText('')
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="mt-3 space-y-2">
      <input
        value={text}
        onChange={(e) => setText(e.target.value)}
        maxLength={500}
        placeholder={placeholder}
        aria-label={placeholder}
        className="block h-10 w-full rounded-lg border border-navy-900/20 bg-white px-3 text-sm text-navy-900 focus:border-teal-600 focus:outline-2 focus:outline-teal-600"
      />
      <div className="flex flex-wrap gap-2">
        <Button onClick={() => void go(true)} disabled={busy || short}>
          Verify
        </Button>
        <Button variant="secondary" onClick={() => void go(false)} disabled={busy || text.trim().length < rejectMin}>
          Reject
        </Button>
        {short && <span className="self-center text-xs text-navy-600">Write at least {minLength} characters about what you checked.</span>}
      </div>
    </div>
  )
}

export default function AdminPage() {
  const { status, user } = useAuth()
  const { replace } = useRouter()
  const [stats, setStats] = useState<AdminStats | null>(null)
  const [techs, setTechs] = useState<AdminTechnician[]>([])
  const [cases, setCases] = useState<RepairCase[]>([])
  const [escalations, setEscalations] = useState<SafetyEscalation[]>([])
  const [error, setError] = useState<ApiError | null>(null)
  const [message, setMessage] = useState<string | null>(null)

  useEffect(() => {
    if (status === 'signedOut') replace(loginUrl(ROUTES.admin))
  }, [status, replace])

  const load = useCallback(async () => {
    try {
      const [s, t1, t2, c, e] = await Promise.all([
        api.adminStats(),
        api.adminTechnicians('pending'),
        api.adminTechnicians('unverified'),
        api.adminCases('unverified'),
        api.adminEscalations(),
      ])
      setStats(s)
      setTechs([...t1.technicians, ...t2.technicians.filter((t) => !t.is_sample)])
      setCases(c.cases)
      setEscalations(e.items)
      setError(null)
    } catch (err) {
      setError(err instanceof ApiError ? err : new ApiError(0, 'unknown', 'Something went wrong.'))
    }
  }, [])

  useEffect(() => {
    if (status === 'signedIn' && user?.role === 'admin') void load()
  }, [status, user, load])

  const act = async (fn: () => Promise<unknown>, done: string) => {
    setMessage(null)
    try {
      await fn()
      setMessage(done)
      await load()
    } catch (err) {
      setError(err instanceof ApiError ? err : new ApiError(0, 'unknown', 'Something went wrong.'))
    }
  }

  if (status !== 'signedIn' || !user) {
    return (
      <PageContainer>
        <div className="flex items-center gap-3 text-navy-700" role="status">
          <Spinner /> Loading…
        </div>
      </PageContainer>
    )
  }
  if (user.role !== 'admin') {
    return (
      <PageContainer>
        <PageHeader title="Admin" documentTitle="Admin" />
        <div className="mt-8 max-w-2xl">
          <Alert tone="error" title="Admins only">
            This page is only for MENDORA admin accounts.
          </Alert>
        </div>
      </PageContainer>
    )
  }

  return (
    <PageContainer>
      <PageHeader title="Admin dashboard" documentTitle="Admin" intro="Verify technicians and repair cases, and keep an eye on high-risk reports." />
      {error && (
        <div className="mt-6">
          <Alert tone="error" announce title="Something didn’t load" action={<Button variant="secondary" onClick={() => void load()}>Try again</Button>}>
            {error.message}
          </Alert>
        </div>
      )}
      {message && (
        <div className="mt-6">
          <Alert tone="success" announce title={message} />
        </div>
      )}
      {!stats ? (
        <div className="mt-8 flex items-center gap-3 text-navy-700" role="status">
          <Spinner /> Loading dashboard…
        </div>
      ) : (
        <>
          <section className="mt-8 grid grid-cols-2 gap-3 md:grid-cols-4" aria-label="Summary">
            <Stat label="Users" value={sum(stats.users)} hint={Object.entries(stats.users).map(([k, v]) => `${v} ${k}`).join(' · ')} />
            <Stat label="Repair requests" value={stats.repair_requests.total} hint={`${stats.repair_requests.by_risk.high ?? 0} high risk`} />
            <Stat label="Bookings" value={sum(stats.bookings)} hint={`${stats.bookings.requested ?? 0} waiting · ${stats.bookings.completed ?? 0} completed`} />
            <Stat
              label="Sandbox payments"
              value={stats.payments_sandbox.by_status.succeeded ?? 0}
              hint={stats.payments_sandbox.succeeded_totals.map((t) => `${t.currency} ${t.amount}`).join(', ') || 'No real money'}
            />
            <Stat label="Technicians" value={sum(stats.technicians.by_verification)} hint={`${stats.technicians.by_verification.verified ?? 0} verified · ${stats.technicians.samples} demo samples`} />
            <Stat label="Repair cases" value={sum(stats.repair_cases)} hint={`${stats.repair_cases.unverified ?? 0} to check`} />
            <Stat label="Reviews" value={stats.reviews.count} hint={stats.reviews.average != null ? `Average ${stats.reviews.average} / 5` : 'None yet'} />
            <div className="rounded-xl border border-navy-900/10 bg-white p-4 text-xs text-navy-700">
              <p className="font-semibold tracking-wide text-navy-600 uppercase">System</p>
              <p className="mt-1">
                AI diagnosis:{' '}
                {stats.system.ai_diagnosis.configured ? <Badge tone="teal">{stats.system.ai_diagnosis.provider} set</Badge> : <Badge tone="amber">not set up</Badge>}
              </p>
              <p className="mt-1">
                Web research: {stats.system.web_research.configured ? <Badge tone="teal">Tavily set</Badge> : <Badge tone="amber">not set up</Badge>}
              </p>
              <p className="mt-1">Payments: {stats.system.payments_provider} · Demo mode: {stats.system.demo_mode ? 'on' : 'off'}</p>
            </div>
          </section>

          <div className="mt-8 grid grid-cols-1 gap-6 lg:grid-cols-2">
            <section className="rounded-2xl border border-navy-900/10 bg-white p-5" aria-labelledby="techq">
              <h2 id="techq" className="font-semibold text-navy-900">
                Technicians to verify <span className="font-normal text-navy-600">({techs.length})</span>
              </h2>
              {techs.length === 0 ? (
                <p className="mt-3 text-sm text-navy-600">Nothing waiting. Demo samples can’t be verified.</p>
              ) : (
                <ul className="mt-3 space-y-4">
                  {techs.map((t) => (
                    <li key={t.id} className="rounded-xl border border-navy-900/10 p-4 text-sm">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-semibold text-navy-900">{t.display_name}</span>
                        <Badge tone={t.verification_status === 'pending' ? 'amber' : 'navy'}>{t.verification_status}</Badge>
                      </div>
                      <p className="mt-1 text-navy-700">
                        {t.trade} · {t.service_areas.join(', ')} · {t.years_experience ?? '?'} yrs (self-reported)
                      </p>
                      {t.skills.length > 0 && <p className="text-navy-600">Skills: {t.skills.join(', ')}</p>}
                      <DecisionForm
                        placeholder="What did you check? e.g. ID and trade licence seen in person"
                        minLength={10}
                        rejectMin={10}
                        onSubmit={(note, approve) => act(() => api.adminVerifyTechnician(t.id, approve ? 'verified' : 'rejected', note), approve ? 'Technician verified.' : 'Technician rejected.')}
                      />
                    </li>
                  ))}
                </ul>
              )}
            </section>

            <section className="rounded-2xl border border-navy-900/10 bg-white p-5" aria-labelledby="caseq">
              <h2 id="caseq" className="font-semibold text-navy-900">
                Repair cases to check <span className="font-normal text-navy-600">({cases.length})</span>
              </h2>
              <p className="mt-1 text-xs text-navy-600">Only technician-confirmed causes can be verified. Verified cases appear (anonymised) as “similar repairs”.</p>
              {cases.length === 0 ? (
                <p className="mt-3 text-sm text-navy-600">Nothing waiting.</p>
              ) : (
                <ul className="mt-3 space-y-4">
                  {cases.map((c) => (
                    <li key={c.id} className="rounded-xl border border-navy-900/10 p-4 text-sm">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-semibold text-navy-900">{c.confirmed_cause ?? 'No cause recorded'}</span>
                        <Badge tone="navy">{c.trade}</Badge>
                        <Badge tone={c.cause_source === 'technician_confirmed' ? 'teal' : 'amber'}>{c.cause_source.replace('_', ' ')}</Badge>
                      </div>
                      <p className="mt-1 line-clamp-3 text-navy-700">{c.symptoms}</p>
                      {c.parts_used.length > 0 && <p className="text-navy-600">Parts: {c.parts_used.join(', ')}</p>}
                      <DecisionForm
                        placeholder="Basis for verifying (min 15 characters), or reason to reject"
                        minLength={15}
                        onSubmit={(text, approve) => act(() => (approve ? api.adminVerifyCase(c.id, text) : api.adminRejectCase(c.id, text)), approve ? 'Repair case verified.' : 'Repair case rejected.')}
                      />
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </div>

          <section className="mt-6 rounded-2xl border border-red-700/20 bg-white p-5" aria-labelledby="escq">
            <h2 id="escq" className="font-semibold text-navy-900">
              High-risk reports <span className="font-normal text-navy-600">({escalations.length})</span>
            </h2>
            <p className="mt-1 text-xs text-navy-600">These never get AI diagnosis or DIY guidance. Contact details are hidden.</p>
            {escalations.length === 0 ? (
              <p className="mt-3 text-sm text-navy-600">None.</p>
            ) : (
              <ul className="mt-3 divide-y divide-navy-900/10">
                {escalations.map((e) => (
                  <li key={e.request_id} className="py-3 text-sm">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge tone="red" icon="alert">
                        {e.trade}
                      </Badge>
                      {e.hazards.map((h) => (
                        <span key={h} className="text-xs text-red-900">
                          {h}
                        </span>
                      ))}
                      <span className="text-xs text-navy-600">{e.created_at ? formatDate(e.created_at) : ''}</span>
                    </div>
                    <p className="mt-1 text-navy-700">{e.description}</p>
                    <p className="mt-0.5 text-xs text-navy-600">
                      {e.bookings} booking(s) ·{' '}
                      <Link to={requestUrl(e.request_id)} className="text-teal-800 underline">
                        Open request
                      </Link>
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </>
      )}
    </PageContainer>
  )
}
