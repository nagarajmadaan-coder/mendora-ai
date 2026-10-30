import { useCallback, useEffect, useState } from 'react'
import PageHeader, { PageContainer } from '../components/PageHeader'
import DiagnosisCard from '../components/diagnosis/DiagnosisCard'
import SafetyPanel from '../components/safety/SafetyPanel'
import KnowledgeGuidance from '../components/knowledge/KnowledgeGuidance'
import WebResearchPanel from '../components/research/WebResearchPanel'
import RequestPhotos from '../components/photos/RequestPhotos'
import Alert from '../components/Alert'
import Badge from '../components/Badge'
import Button from '../components/Button'
import Icon from '../components/Icon'
import Spinner from '../components/Spinner'
import { ApiError, api, type ClarifyingAnswer, type FollowUpAnswer, type RepairRequest } from '../lib/api'
import { ROUTES, TRADES, loginUrl, requestUrl, techniciansUrl } from '../data/content'
import { useAuth } from '../state/AuthContext'
import { useIntake } from '../state/IntakeContext'

/*
  One saved repair request (URL: /requests/<id>).

  Order on the page:  what you reported → SAFETY RESULT → AI diagnosis (only if safety allows it).
  - high risk:   safety advice only. No diagnosis section, no diagnosis button.
  - medium risk: safety questions; an optional professional-only AI assessment (no DIY steps).
  - low risk:    "Get AI diagnosis".
  The server enforces all of this too, so the page can't be used to get around it.
*/

type DiagnosisState = { kind: 'idle' } | { kind: 'running' } | { kind: 'error'; error: ApiError }

const RETRYABLE = new Set(['ai_timeout', 'ai_rate_limited', 'ai_provider_error', 'ai_invalid_response', 'network_error', 'ai_not_configured', 'too_many_requests'])

function diagnosisErrorTitle(code: string): string {
  switch (code) {
    case 'ai_not_configured':
      return 'AI diagnosis isn’t set up on this server yet'
    case 'network_error':
      return 'Couldn’t reach the MENDORA server'
    case 'ai_timeout':
      return 'The AI took too long to respond'
    case 'ai_rate_limited':
    case 'too_many_requests':
      return 'Too many requests right now'
    case 'not_authenticated':
      return 'Please sign in again'
    default:
      return 'No diagnosis could be generated'
  }
}

function toApiError(err: unknown): ApiError {
  return err instanceof ApiError ? err : new ApiError(0, 'unknown', 'Something went wrong.')
}

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
}

export default function RequestPage({ requestId }: { requestId: string }) {
  const { status: authStatus } = useAuth()
  const { setLastRequest } = useIntake()

  const [request, setRequest] = useState<RepairRequest | null>(null)
  const [loadError, setLoadError] = useState<ApiError | null>(null)
  const [diagnosis, setDiagnosis] = useState<DiagnosisState>({ kind: 'idle' })
  const [answering, setAnswering] = useState(false)
  const [answerError, setAnswerError] = useState<string | null>(null)
  const [escalated, setEscalated] = useState(false)

  const accept = useCallback(
    (r: RepairRequest) => {
      setRequest(r)
      setLastRequest(r)
    },
    [setLastRequest],
  )

  // Load the request (after we know whether the user is signed in).
  useEffect(() => {
    if (authStatus === 'loading') return
    let cancelled = false
    setLoadError(null)
    api
      .getRepairRequest(requestId)
      .then((r) => !cancelled && accept(r))
      .catch((err) => !cancelled && setLoadError(toApiError(err)))
    return () => {
      cancelled = true
    }
  }, [requestId, authStatus, accept])

  const runDiagnosis = useCallback(
    async (answers: FollowUpAnswer[] = []) => {
      setDiagnosis({ kind: 'running' })
      setEscalated(false)
      try {
        const updated = await api.diagnose(requestId, answers)
        accept(updated)
        if (updated.safety.risk_level === 'high') setEscalated(true)
        setDiagnosis({ kind: 'idle' })
      } catch (err) {
        const error = toApiError(err)
        if (error.code === 'blocked_by_safety') {
          // The server's safety check said no. Reload so the page shows the current safety advice.
          const fresh = await api.getRepairRequest(requestId).catch(() => null)
          if (fresh) accept(fresh)
          setEscalated(true)
          setDiagnosis({ kind: 'idle' })
          return
        }
        setDiagnosis({ kind: 'error', error })
      }
    },
    [requestId, accept],
  )

  const answerSafety = useCallback(
    async (answers: ClarifyingAnswer[]) => {
      setAnswering(true)
      setAnswerError(null)
      try {
        accept(await api.answerSafetyQuestions(requestId, answers))
      } catch (err) {
        setAnswerError(toApiError(err).message)
      } finally {
        setAnswering(false)
      }
    },
    [requestId, accept],
  )

  /* ---------- Loading / errors for the request itself ---------- */

  if (loadError) {
    const notFound = loadError.status === 404
    return (
      <PageContainer>
        <PageHeader title="Repair request" documentTitle="Repair request" backFallback={ROUTES.account} />
        <div className="mt-8 max-w-2xl">
          <Alert
            tone="error"
            title={notFound ? 'We couldn’t find this request' : 'This request couldn’t be loaded'}
            action={
              <div className="flex flex-wrap gap-3">
                {notFound && authStatus !== 'signedIn' ? (
                  <Button to={loginUrl(requestUrl(requestId))}>Sign in</Button>
                ) : (
                  <Button to={ROUTES.account}>My requests</Button>
                )}
                <Button to={ROUTES.diagnose} variant="secondary">
                  Start a new request
                </Button>
              </div>
            }
          >
            {notFound
              ? authStatus === 'signedIn'
                ? 'It may not exist, or it may belong to a different account.'
                : 'If you created it while signed in, sign in to view it.'
              : loadError.message}
          </Alert>
        </div>
      </PageContainer>
    )
  }

  if (!request) {
    return (
      <PageContainer>
        <PageHeader title="Repair request" documentTitle="Repair request" backFallback={ROUTES.account} />
        <div className="mt-10 flex items-center gap-3 text-navy-700" role="status">
          <Spinner /> Loading your request…
        </div>
      </PageContainer>
    )
  }

  /* ---------- The request, its safety result, and (if allowed) the diagnosis ---------- */

  const trade = TRADES.find((t) => t.id === request.trade.id)
  const safety = request.safety
  const running = diagnosis.kind === 'running'
  const canAct = request.owned_by_account ? authStatus === 'signedIn' : true
  const canDiagnose = request.owned_by_account && authStatus === 'signedIn' && safety.risk_level !== 'high'

  return (
    <PageContainer>
      <PageHeader
        title={`${request.trade.name} request`}
        documentTitle={`${request.trade.name} request`}
        backFallback={ROUTES.account}
        aside={
          safety.risk_level === 'high' ? (
            <Badge tone="red" icon="alert">
              High risk
            </Badge>
          ) : request.diagnosis_status === 'completed' ? (
            <Badge tone="teal" icon="checkCircle">
              Assessed
            </Badge>
          ) : safety.risk_level === 'medium' ? (
            <Badge tone="amber" icon="shield">
              Safety check needed
            </Badge>
          ) : (
            <Badge tone="navy">Saved</Badge>
          )
        }
        intro={`Submitted ${formatDate(request.created_at)}`}
      />

      <div className="mt-8 grid grid-cols-1 gap-8 lg:grid-cols-[1fr_20rem] lg:items-start">
        <div className="space-y-6">
          <section aria-labelledby="reported-heading" className="rounded-2xl border border-navy-900/10 bg-white p-5 sm:p-6">
            <h2 id="reported-heading" className="flex items-center gap-3 font-semibold text-navy-900">
              <span className="flex size-10 items-center justify-center rounded-lg bg-navy-900 text-teal-300">
                <Icon name={trade?.icon ?? 'home'} className="size-5" />
              </span>
              What you reported
            </h2>
            <p className="mt-4 leading-relaxed break-words whitespace-pre-wrap text-navy-800">{request.description}</p>
          </section>

          {request.owned_by_account && authStatus === 'signedIn' && <RequestPhotos requestId={request.request_id} canEdit />}

          {escalated && safety.risk_level === 'high' && (
            <Alert tone="error" announce title="Safety advice now applies to this request">
              The safety check found a possible danger, so no diagnosis or repair steps will be shown. Please follow the advice below.
            </Alert>
          )}

          <SafetyPanel
            key={safety.assessed_at}
            assessment={safety}
            onAnswer={canAct ? (a) => void answerSafety(a) : undefined}
            answering={answering}
            answerError={answerError}
          />

          {safety.risk_level !== 'high' && <KnowledgeGuidance requestId={request.request_id} safetyKey={safety.assessed_at} />}

          {safety.risk_level !== 'high' && request.owned_by_account && authStatus === 'signedIn' && (
            <WebResearchPanel key={`web-${safety.assessed_at}`} requestId={request.request_id} />
          )}

          {safety.risk_level !== 'high' && (
            <div className="rounded-2xl border border-navy-900/10 bg-white p-5 shadow-sm sm:p-8" aria-live="polite">
              {running && !request.diagnosis ? (
                <div role="status" className="flex flex-col items-center gap-4 py-10 text-center">
                  <Spinner className="size-10 text-teal-700" label="Analysing" />
                  <div>
                    <p className="text-lg font-semibold text-navy-900">Analysing your description…</p>
                    <p className="mt-1 text-sm text-navy-600">This usually takes 10–30 seconds.</p>
                  </div>
                </div>
              ) : request.diagnosis ? (
                <DiagnosisCard
                  key={request.diagnosed_at ?? 'diagnosis'}
                  diagnosis={request.diagnosis}
                  busy={running}
                  onAnswer={canDiagnose ? (answers) => void runDiagnosis(answers) : undefined}
                />
              ) : (
                <div className="space-y-4">
                  <h2 className="text-xl font-semibold text-navy-900">AI assessment</h2>
                  {!request.owned_by_account ? (
                    <Alert tone="info" title="Sign-in needed for AI diagnosis">
                      This request was saved without an account. To get an AI diagnosis, sign in and submit a new request.
                    </Alert>
                  ) : safety.risk_level === 'medium' ? (
                    <p className="leading-relaxed text-navy-700">
                      You can get an AI assessment that explains what might be wrong. Because of the possible risk, it won’t include do-it-yourself repair steps
                      {safety.clarifying_questions.length > 0 ? ' — answering the safety questions above first may give you a fuller result.' : '.'}
                    </p>
                  ) : (
                    <p className="text-navy-700">The safety check allows an AI diagnosis for this request.</p>
                  )}
                  {canDiagnose && diagnosis.kind !== 'error' && (
                    <Button onClick={() => void runDiagnosis()} disabled={answering}>
                      <Icon name="sparkles" className="size-4" />
                      {safety.risk_level === 'medium' ? 'Get professional-only AI assessment' : 'Get AI diagnosis'}
                    </Button>
                  )}
                </div>
              )}

              {diagnosis.kind === 'error' && (
                <div className="mt-5">
                  <Alert
                    tone={diagnosis.error.code === 'ai_not_configured' ? 'warning' : 'error'}
                    announce
                    title={diagnosisErrorTitle(diagnosis.error.code)}
                    action={
                      diagnosis.error.code === 'not_authenticated' ? (
                        <Button to={loginUrl(requestUrl(requestId))}>Sign in</Button>
                      ) : RETRYABLE.has(diagnosis.error.code) ? (
                        <Button variant="secondary" onClick={() => void runDiagnosis()}>
                          Try again
                        </Button>
                      ) : undefined
                    }
                  >
                    {diagnosis.error.message}
                    {request.diagnosis && ' Your earlier assessment is still shown above.'} The safety result above still applies.
                  </Alert>
                </div>
              )}
            </div>
          )}
        </div>

        <aside className="space-y-5" aria-label="Next steps">
          <div className="rounded-2xl border border-navy-900/10 bg-white p-5">
            <h2 className="font-semibold text-navy-900">What next?</h2>
            <div className="mt-4 flex flex-col gap-3">
              {request.owned_by_account && authStatus === 'signedIn' && (
                <>
                  <Button to={techniciansUrl({ trade: request.trade.id, request: request.request_id })}>
                    <Icon name="user" className="size-4" />
                    Find a technician
                  </Button>
                  <Button to={techniciansUrl({ trade: request.trade.id, consultation: true, request: request.request_id })} variant="secondary">
                    <Icon name="message" className="size-4" />
                    Talk to an expert
                  </Button>
                  {safety.risk_level === 'high' && (
                    <p className="text-xs leading-relaxed text-navy-600">
                      Booking help doesn’t change the safety advice. Make sure you’re safe first — MENDORA is not an emergency service.
                    </p>
                  )}
                </>
              )}
              <Button to={ROUTES.resolutions} variant="secondary">
                View resolution options
              </Button>
              {authStatus === 'signedIn' && (
                <Button to={ROUTES.account} variant="secondary">
                  My requests
                </Button>
              )}
              <Button to={ROUTES.diagnose} variant="secondary">
                Start a new request
              </Button>
            </div>
          </div>
          <div className="rounded-2xl border border-red-700/20 bg-red-50 p-5 text-sm leading-relaxed text-red-900">
            <p className="flex items-center gap-2 font-semibold">
              <Icon name="alert" className="size-4" /> Safety first
            </p>
            <p className="mt-2">{request.safety_notice}</p>
          </div>
        </aside>
      </div>
    </PageContainer>
  )
}
