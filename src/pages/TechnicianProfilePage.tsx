import { useEffect, useState, type FormEvent } from 'react'
import PageHeader, { PageContainer } from '../components/PageHeader'
import Alert from '../components/Alert'
import Badge from '../components/Badge'
import Button from '../components/Button'
import Spinner from '../components/Spinner'
import TextField from '../components/TextField'
import { useRouter } from '../lib/router'
import { ApiError, api, type Availability, type TechnicianProfile } from '../lib/api'
import { ROUTES, TRADES, loginUrl } from '../data/content'
import { useAuth } from '../state/AuthContext'
import type { TradeId } from '../types'

/*
  My technician profile (URL: /technician/profile) — technician accounts only.
  - Edit your public profile and set your availability.
  - Verification can only be granted by a MENDORA admin; here you can only ask for it.
  - Until you're verified, customers can't find or book you.
*/

const VERIFY_TONE = { unverified: 'navy', pending: 'amber', verified: 'teal', rejected: 'red' } as const

function toApiError(err: unknown): ApiError {
  return err instanceof ApiError ? err : new ApiError(0, 'unknown', 'Something went wrong. Please try again.')
}

const list = (s: string) =>
  s
    .split(',')
    .map((x) => x.trim())
    .filter(Boolean)
const num = (s: string) => (s.trim() === '' ? null : Number(s))

export default function TechnicianProfilePage() {
  const { status, user } = useAuth()
  const { replace } = useRouter()
  const [profile, setProfile] = useState<TechnicianProfile | null>(null)
  const [loaded, setLoaded] = useState(false)
  const [loadError, setLoadError] = useState<ApiError | null>(null)

  const [name, setName] = useState('')
  const [trade, setTrade] = useState<TradeId>('plumbing')
  const [areas, setAreas] = useState('')
  const [skills, setSkills] = useState('')
  const [years, setYears] = useState('')
  const [bio, setBio] = useState('')
  const [visitRate, setVisitRate] = useState('')
  const [consultRate, setConsultRate] = useState('')

  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)
  const [message, setMessage] = useState<string | null>(null)

  useEffect(() => {
    if (status === 'signedOut') replace(loginUrl(ROUTES.technicianProfile))
  }, [status, replace])

  const fill = (p: TechnicianProfile) => {
    setProfile(p)
    setName(p.display_name)
    setTrade(p.trade)
    setAreas(p.service_areas.join(', '))
    setSkills(p.skills.join(', '))
    setYears(p.years_experience?.toString() ?? '')
    setBio(p.bio ?? '')
    setVisitRate(p.visit_rate?.toString() ?? '')
    setConsultRate(p.consultation_rate?.toString() ?? '')
  }

  useEffect(() => {
    if (status !== 'signedIn' || user?.role !== 'technician') return
    api
      .getMyTechnicianProfile()
      .then(fill)
      .catch((err) => {
        const e = toApiError(err)
        if (e.status !== 404) setLoadError(e) // 404 = no profile yet: show an empty form
      })
      .finally(() => setLoaded(true))
  }, [status, user])

  const save = async (e: FormEvent) => {
    e.preventDefault()
    setSaving(true)
    setError(null)
    setMessage(null)
    try {
      const p = await api.saveMyTechnicianProfile({
        display_name: name.trim(),
        trade,
        service_areas: list(areas),
        skills: list(skills),
        years_experience: num(years),
        bio: bio.trim() || null,
        visit_rate: num(visitRate),
        consultation_rate: num(consultRate),
      })
      fill(p)
      setMessage('Profile saved.')
    } catch (err) {
      setError(toApiError(err))
    } finally {
      setSaving(false)
    }
  }

  const act = async (fn: () => Promise<TechnicianProfile>, done: string) => {
    setError(null)
    setMessage(null)
    try {
      fill(await fn())
      setMessage(done)
    } catch (err) {
      setError(toApiError(err))
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

  if (user.role !== 'technician') {
    return (
      <PageContainer>
        <PageHeader title="Technician profile" documentTitle="Technician profile" />
        <div className="mt-8 max-w-2xl">
          <Alert tone="info" title="For technician accounts">
            Technician accounts are created by a MENDORA admin. You’re signed in as a {user.role}.
          </Alert>
        </div>
      </PageContainer>
    )
  }

  if (!loaded) {
    return (
      <PageContainer>
        <PageHeader title="My technician profile" documentTitle="Technician profile" />
        <div className="mt-10 flex items-center gap-3 text-navy-700" role="status">
          <Spinner /> Loading your profile…
        </div>
      </PageContainer>
    )
  }

  if (loadError) {
    return (
      <PageContainer>
        <PageHeader title="My technician profile" documentTitle="Technician profile" />
        <div className="mt-8 max-w-2xl">
          <Alert tone="error" title="Your profile couldn’t be loaded">
            {loadError.message}
          </Alert>
        </div>
      </PageContainer>
    )
  }

  const field = (f: string) => error?.fieldMessage(f) ?? null
  const isSample = profile?.is_sample ?? false
  const areaClass =
    'mt-2 block w-full rounded-xl border border-navy-900/20 bg-white px-4 py-3 text-base text-navy-900 focus:border-teal-600 focus:outline-2 focus:outline-teal-600'

  return (
    <PageContainer>
      <PageHeader
        title="My technician profile"
        documentTitle="Technician profile"
        aside={profile && <Badge tone={VERIFY_TONE[profile.verification_status]}>{profile.verification_label}</Badge>}
        intro="Customers see your name, trade, areas, skills, experience and rates — never your email or phone number."
      />

      <div className="mt-8 grid grid-cols-1 gap-8 lg:grid-cols-[1fr_20rem] lg:items-start">
        <form onSubmit={(e) => void save(e)} noValidate className="space-y-5 rounded-2xl border border-navy-900/10 bg-white p-5 sm:p-6">
          {isSample && (
            <Alert tone="warning" title="Demo sample profile">
              This is a made-up sample account for testing, so it can’t be edited or verified.
            </Alert>
          )}
          {message && <Alert tone="success" announce title={message} />}
          {error && !error.details.length && (
            <Alert tone="error" announce title="That didn’t work">
              {error.message}
            </Alert>
          )}
          <TextField id="t-name" label="Display name" value={name} onChange={(e) => setName(e.target.value)} maxLength={80} error={field('display_name')} disabled={isSample} />
          <div>
            <label htmlFor="t-trade" className="block text-sm font-semibold text-navy-900">
              Trade
            </label>
            <select
              id="t-trade"
              value={trade}
              disabled={isSample}
              onChange={(e) => setTrade(e.target.value as TradeId)}
              className="mt-2 block h-12 w-full rounded-xl border border-navy-900/20 bg-white px-3 text-base text-navy-900 focus:border-teal-600 focus:outline-2 focus:outline-teal-600"
            >
              {TRADES.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </select>
            {profile?.verification_status === 'verified' && trade !== profile.trade && (
              <p className="mt-1 text-sm text-amber-800">Changing your trade removes your verification until an admin checks again.</p>
            )}
          </div>
          <TextField
            id="t-areas"
            label="Areas you serve"
            hint="Postal codes or area names, separated by commas — e.g. 560001, Indiranagar"
            value={areas}
            onChange={(e) => setAreas(e.target.value)}
            error={field('service_areas')}
            disabled={isSample}
          />
          <TextField id="t-skills" label="Skills" hint="Separated by commas" value={skills} onChange={(e) => setSkills(e.target.value)} error={field('skills')} disabled={isSample} />
          <TextField id="t-years" label="Years of experience" type="number" min={0} max={60} value={years} onChange={(e) => setYears(e.target.value)} error={field('years_experience')} disabled={isSample} />
          <div>
            <label htmlFor="t-bio" className="block text-sm font-semibold text-navy-900">
              About you <span className="font-normal text-navy-600">(optional)</span>
            </label>
            <textarea id="t-bio" value={bio} onChange={(e) => setBio(e.target.value)} maxLength={600} rows={3} className={areaClass} disabled={isSample} />
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <TextField id="t-visit" label="Visit rate (optional)" type="number" min={0} value={visitRate} onChange={(e) => setVisitRate(e.target.value)} error={field('visit_rate')} disabled={isSample} />
            <TextField
              id="t-consult"
              label="Consultation rate, 30 min"
              hint="Leave empty if you don’t offer consultations"
              type="number"
              min={0}
              value={consultRate}
              onChange={(e) => setConsultRate(e.target.value)}
              error={field('consultation_rate')}
              disabled={isSample}
            />
          </div>
          {error && error.details.length > 0 && (
            <Alert tone="error" announce title="Please check the highlighted fields">
              {error.details.filter((d) => !d.field).map((d) => d.message).join(' ') || null}
            </Alert>
          )}
          {!isSample && (
            <Button type="submit" disabled={saving}>
              {saving && <Spinner />}
              {profile ? 'Save changes' : 'Create profile'}
            </Button>
          )}
        </form>

        <aside className="space-y-5" aria-label="Verification and availability">
          <div className="rounded-2xl border border-navy-900/10 bg-white p-5">
            <h2 className="font-semibold text-navy-900">Verification</h2>
            {!profile ? (
              <p className="mt-2 text-sm text-navy-700">Create your profile first.</p>
            ) : (
              <>
                <p className="mt-2 text-sm text-navy-700">
                  {profile.verification_status === 'verified'
                    ? 'Customers can find and book you.'
                    : profile.verification_status === 'pending'
                      ? 'Waiting for a MENDORA admin to check your details.'
                      : 'Customers can’t see you until a MENDORA admin verifies your profile.'}
                </p>
                {profile.verification_note && <p className="mt-2 text-sm text-navy-600">Admin note: {profile.verification_note}</p>}
                {!isSample && (profile.verification_status === 'unverified' || profile.verification_status === 'rejected') && (
                  <Button className="mt-4 w-full" onClick={() => void act(api.submitForVerification, 'Sent to an admin for verification.')}>
                    Ask for verification
                  </Button>
                )}
              </>
            )}
          </div>
          {profile && (
            <div className="rounded-2xl border border-navy-900/10 bg-white p-5">
              <h2 className="font-semibold text-navy-900">Availability</h2>
              <div className="mt-3 flex flex-col gap-2" role="radiogroup" aria-label="Availability">
                {(
                  [
                    ['available', 'Accepting requests'],
                    ['busy', 'Busy (still listed)'],
                    ['unavailable', 'Not taking requests'],
                  ] as [Availability, string][]
                ).map(([value, label]) => (
                  <label key={value} className="flex items-center gap-2 text-sm text-navy-800">
                    <input
                      type="radio"
                      name="availability"
                      checked={profile.availability_status === value}
                      onChange={() => void act(() => api.setAvailability(value), 'Availability updated.')}
                      className="accent-teal-700"
                    />
                    {label}
                  </label>
                ))}
              </div>
            </div>
          )}
          <Button to={ROUTES.bookings} variant="secondary" className="w-full">
            Assigned bookings
          </Button>
        </aside>
      </div>
    </PageContainer>
  )
}
