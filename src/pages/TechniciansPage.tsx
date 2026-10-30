import { useCallback, useEffect, useState, type FormEvent } from 'react'
import PageHeader, { PageContainer } from '../components/PageHeader'
import Alert from '../components/Alert'
import Badge from '../components/Badge'
import Button from '../components/Button'
import Icon from '../components/Icon'
import Spinner from '../components/Spinner'
import Stars from '../components/reviews/Stars'
import TechnicianMap from '../components/technicians/TechnicianMap'
import { useRouter } from '../lib/router'
import { ApiError, api, type Technician, type TechnicianSearchResult } from '../lib/api'
import { ROUTES, TRADES, bookUrl } from '../data/content'
import type { TradeId } from '../types'

/*
  Find a technician (URL: /technicians).
  - Filters: trade, service area (postal code or area name), available now, offers consultations.
  - Results are matched by trade and SERVICE AREA, not distance — nobody is described as "nearest".
  - Only admin-verified technicians appear, plus clearly-labelled demo samples when demo mode is on.
  - ?request=<id> carries the user's repair request through to the booking screen.
*/

export function money(amount: number | null, currency: string): string {
  if (amount == null) return 'Rate to be confirmed'
  try {
    return new Intl.NumberFormat(undefined, { style: 'currency', currency, maximumFractionDigits: 0 }).format(amount)
  } catch {
    return `${currency} ${amount}`
  }
}

const AVAILABILITY: Record<Technician['availability_status'], { label: string; tone: 'teal' | 'amber' | 'navy' }> = {
  available: { label: 'Accepting requests', tone: 'teal' },
  busy: { label: 'Busy — may respond slowly', tone: 'amber' },
  unavailable: { label: 'Not taking requests', tone: 'navy' },
}

function readFilters(search: string) {
  const p = new URLSearchParams(search)
  const trade = p.get('trade')
  return {
    trade: (TRADES.some((t) => t.id === trade) ? trade : '') as TradeId | '',
    area: p.get('area') ?? '',
    available: p.get('available') === '1',
    consultation: p.get('consultation') === '1',
    request: p.get('request') ?? undefined,
  }
}

export function TechnicianBadges({ t }: { t: Pick<Technician, 'is_sample' | 'verification_status' | 'verification_label'> }) {
  return t.is_sample ? (
    <Badge tone="amber" icon="info">
      Demo sample — not a real technician
    </Badge>
  ) : t.verification_status === 'verified' ? (
    <Badge tone="teal" icon="checkCircle">
      {t.verification_label}
    </Badge>
  ) : (
    <Badge tone="navy">{t.verification_label}</Badge>
  )
}

export default function TechniciansPage() {
  const { location, replace } = useRouter()
  const initial = readFilters(location.search)
  const [trade, setTrade] = useState<TradeId | ''>(initial.trade)
  const [area, setArea] = useState(initial.area)
  const [available, setAvailable] = useState(initial.available)
  const [consultation, setConsultation] = useState(initial.consultation)
  const requestId = initial.request

  const [result, setResult] = useState<TechnicianSearchResult | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [loading, setLoading] = useState(false)

  const search = useCallback(async (f: { trade: TradeId | ''; area: string; available: boolean; consultation: boolean }) => {
    setLoading(true)
    setError(null)
    try {
      setResult(await api.searchTechnicians(f))
    } catch (err) {
      setError(err instanceof ApiError ? err : new ApiError(0, 'unknown', 'Something went wrong.'))
    } finally {
      setLoading(false)
    }
  }, [])

  // First load uses the filters from the link.
  useEffect(() => {
    void search(initial)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search])

  const onSubmit = (e: FormEvent) => {
    e.preventDefault()
    const q = new URLSearchParams()
    if (trade) q.set('trade', trade)
    if (area.trim()) q.set('area', area.trim())
    if (available) q.set('available', '1')
    if (consultation) q.set('consultation', '1')
    if (requestId) q.set('request', requestId)
    const next = q.toString() ? `?${q}` : ''
    // A new URL re-opens this screen with the new filters (so Back/links keep them); same URL → search again here.
    if (next === location.search) void search({ trade, area, available, consultation })
    else replace(`${ROUTES.technicians}${next}`)
  }

  const hasSamples = result?.results.some((r) => r.technician.is_sample)
  const [view, setView] = useState<'list' | 'map'>('list')

  return (
    <PageContainer>
      <PageHeader
        title={consultation ? 'Find an expert' : 'Find a technician'}
        documentTitle="Find a technician"
        intro="Technicians are matched by trade and the areas they serve. Real technicians are listed only after a MENDORA admin verifies them; in demo mode, clearly-labelled sample records are shown too."
      />

      <form onSubmit={onSubmit} className="mt-8 grid grid-cols-1 gap-4 rounded-2xl border border-navy-900/10 bg-white p-5 sm:grid-cols-2 lg:grid-cols-[12rem_1fr_auto] lg:items-end" aria-label="Search filters">
        <div>
          <label htmlFor="f-trade" className="block text-sm font-semibold text-navy-900">
            Trade
          </label>
          <select
            id="f-trade"
            value={trade}
            onChange={(e) => setTrade(e.target.value as TradeId | '')}
            className="mt-2 block h-12 w-full rounded-xl border border-navy-900/20 bg-white px-3 text-base text-navy-900 focus:border-teal-600 focus:outline-2 focus:outline-teal-600"
          >
            <option value="">All trades</option>
            {TRADES.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="f-area" className="block text-sm font-semibold text-navy-900">
            Your area
          </label>
          <input
            id="f-area"
            value={area}
            onChange={(e) => setArea(e.target.value)}
            maxLength={60}
            placeholder="Postal code, area or city — e.g. 560001"
            aria-describedby="f-area-hint"
            className="mt-2 block h-12 w-full rounded-xl border border-navy-900/20 bg-white px-4 text-base text-navy-900 placeholder:text-navy-600/70 focus:border-teal-600 focus:outline-2 focus:outline-teal-600"
          />
        </div>
        <p id="f-area-hint" className="text-xs text-navy-600 sm:col-span-2 lg:col-span-3 lg:-mt-2 lg:order-last">
          Matches the areas technicians list (postal code, neighbourhood or city). Leave empty to see everyone.
        </p>
        <Button type="submit" className="h-12" disabled={loading}>
          <Icon name="search" className="size-4" />
          Search
        </Button>
        <div className="flex flex-wrap gap-x-6 gap-y-2 sm:col-span-2 lg:col-span-3">
          <label className="flex items-center gap-2 text-sm text-navy-800">
            <input type="checkbox" checked={available} onChange={(e) => setAvailable(e.target.checked)} className="size-4 accent-teal-700" />
            Accepting requests now
          </label>
          <label className="flex items-center gap-2 text-sm text-navy-800">
            <input type="checkbox" checked={consultation} onChange={(e) => setConsultation(e.target.checked)} className="size-4 accent-teal-700" />
            Offers expert consultations
          </label>
        </div>
      </form>

      {result && (
        <div className="mt-4 flex flex-wrap items-start justify-between gap-3">
          <p className="max-w-3xl text-sm text-navy-600">{result.sort_note}</p>
          {result.results.length > 0 && (
            <div className="flex rounded-lg bg-white p-1 ring-1 ring-inset ring-navy-900/15" role="group" aria-label="View">
              {(['list', 'map'] as const).map((v) => (
                <button
                  key={v}
                  type="button"
                  aria-pressed={view === v}
                  onClick={() => setView(v)}
                  className={`h-8 rounded-md px-3 text-sm font-medium ${view === v ? 'bg-navy-900 text-white' : 'text-navy-800 hover:bg-navy-50'}`}
                >
                  {v === 'list' ? 'List' : 'Map'}
                </button>
              ))}
            </div>
          )}
        </div>
      )}
      {hasSamples && (
        <div className="mt-4">
          <Alert tone="warning" title="Demo mode: sample technicians">
            Profiles marked “Demo sample” are made-up test records. They are not real people or businesses, are not verified, and nobody will
            actually visit or call.
          </Alert>
        </div>
      )}

      <div className="mt-6" aria-live="polite">
        {error ? (
          <Alert tone="error" announce title="Technicians couldn’t be loaded" action={<Button variant="secondary" onClick={() => void search({ trade, area, available, consultation })}>Try again</Button>}>
            {error.message}
          </Alert>
        ) : !result || (loading && !result) ? (
          <div className="flex items-center gap-3 rounded-2xl border border-navy-900/10 bg-white p-6 text-navy-700" role="status">
            <Spinner /> Finding technicians…
          </div>
        ) : result.results.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-navy-900/20 bg-white p-8 text-center">
            <Icon name="search" className="mx-auto size-8 text-navy-600" />
            <p className="mt-3 font-semibold text-navy-900">No matching technicians</p>
            <p className="mx-auto mt-1 max-w-md text-sm text-navy-600">{result.message}</p>
            {result.covered_areas.length > 0 && (
              <div className="mt-5">
                <p className="text-sm font-semibold text-navy-900">Areas currently covered{trade ? ` for ${trade}` : ''}:</p>
                <div className="mt-2 flex flex-wrap justify-center gap-2">
                  {result.covered_areas.map((a) => (
                    <button
                      key={a}
                      type="button"
                      onClick={() => {
                        setArea(a)
                        void search({ trade, area: a, available, consultation })
                      }}
                      className="h-9 rounded-full bg-white px-3 text-sm font-medium text-navy-800 ring-1 ring-inset ring-navy-900/15 hover:bg-navy-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-600"
                    >
                      {a}
                    </button>
                  ))}
                </div>
              </div>
            )}
            <div className="mt-5">
              <Button
                variant="secondary"
                onClick={() => {
                  setArea('')
                  setAvailable(false)
                  setConsultation(false)
                  void search({ trade, area: '', available: false, consultation: false })
                }}
              >
                Clear area and filters
              </Button>
            </div>
          </div>
        ) : (
          <>
          {view === 'map' && <div className="mb-6"><TechnicianMap results={result.results} searchPoint={result.search_point} /></div>}
          <ul className={`grid grid-cols-1 gap-4 md:grid-cols-2 ${loading ? 'opacity-60' : ''}`}>
            {result.results.map(({ technician: t, match_reasons, approx_distance_km: approx }) => {
              const tradeInfo = TRADES.find((x) => x.id === t.trade)
              const canBook = t.availability_status !== 'unavailable'
              return (
                <li key={t.id} className="flex flex-col rounded-2xl border border-navy-900/10 bg-white p-5">
                  <div className="flex items-start gap-3">
                    <span className="flex size-11 shrink-0 items-center justify-center rounded-lg bg-navy-900 text-teal-300">
                      <Icon name={tradeInfo?.icon ?? 'home'} className="size-5" />
                    </span>
                    <div className="min-w-0 flex-1">
                      <h2 className="font-semibold break-words text-navy-900">{t.display_name}</h2>
                      <p className="text-sm text-navy-600">
                        {tradeInfo?.name ?? t.trade}
                        {t.years_experience != null && ` · ${t.years_experience} years’ experience`}
                      </p>
                    </div>
                  </div>
                  <div className="mt-3 flex flex-wrap gap-2">
                    <TechnicianBadges t={t} />
                    <Badge tone={AVAILABILITY[t.availability_status].tone}>{AVAILABILITY[t.availability_status].label}</Badge>
                  </div>
                  {t.bio && <p className="mt-3 text-sm leading-relaxed text-navy-700">{t.bio}</p>}
                  <dl className="mt-3 grid grid-cols-1 gap-2 text-sm sm:grid-cols-2">
                    <div>
                      <dt className="text-navy-600">Areas served</dt>
                      <dd className="font-medium break-words text-navy-900">{t.service_areas.join(', ')}</dd>
                    </div>
                    {t.skills.length > 0 && (
                      <div>
                        <dt className="text-navy-600">Skills</dt>
                        <dd className="font-medium text-navy-900">{t.skills.join(', ')}</dd>
                      </div>
                    )}
                    <div>
                      <dt className="text-navy-600">Visit (listed rate)</dt>
                      <dd className="font-medium text-navy-900">{money(t.visit_rate, t.currency)}</dd>
                    </div>
                    <div>
                      <dt className="text-navy-600">Consultation, 30 min</dt>
                      <dd className="font-medium text-navy-900">{t.offers_consultation ? money(t.consultation_rate, t.currency) : 'Not offered'}</dd>
                    </div>
                  </dl>
                  <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1">
                    {t.reviews.count > 0 && t.reviews.average != null && <Stars value={t.reviews.average} label={`${t.reviews.average} out of 5`} />}
                    <p className="text-xs text-navy-600">{t.reviews.note}</p>
                  </div>
                  {approx != null && (
                    <p className="mt-1 text-xs text-navy-700">
                      <Icon name="mapPin" className="mr-1 inline size-3.5" />
                      About {approx} km between area centres (approximate)
                    </p>
                  )}
                  <div className="mt-3 rounded-lg bg-navy-50 p-3">
                    <p className="text-xs font-semibold text-navy-800">Why this match</p>
                    <ul className="mt-1 space-y-0.5 text-xs text-navy-700">
                      {match_reasons.map((r) => (
                        <li key={r} className="flex items-start gap-1.5">
                          <Icon name="check" className="mt-px size-3.5 shrink-0 text-teal-700" />
                          {r}
                        </li>
                      ))}
                    </ul>
                  </div>
                  <div className="mt-4 flex flex-wrap gap-3 pt-1">
                    {canBook ? (
                      <>
                        <Button to={bookUrl(t.id, 'technician_visit', requestId)}>Request a visit</Button>
                        {t.offers_consultation && (
                          <Button to={bookUrl(t.id, 'expert_consultation', requestId)} variant="secondary">
                            Book a consultation
                          </Button>
                        )}
                      </>
                    ) : (
                      <p className="text-sm text-navy-600">This technician isn’t taking requests right now.</p>
                    )}
                  </div>
                </li>
              )
            })}
          </ul>
          </>
        )}
      </div>
    </PageContainer>
  )
}
