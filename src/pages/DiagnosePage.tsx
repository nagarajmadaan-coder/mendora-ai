import { useEffect, useRef, useState } from 'react'
import IntakeForm from '../components/intake/IntakeForm'
import PageHeader, { PageContainer } from '../components/PageHeader'
import DangerSignList from '../components/DangerSignList'
import SafetyPanel from '../components/safety/SafetyPanel'
import Alert from '../components/Alert'
import Button from '../components/Button'
import Icon from '../components/Icon'
import Spinner from '../components/Spinner'
import { Link, useRouter } from '../lib/router'
import { fileToBase64 } from '../components/photos/RequestPhotos'
import { ApiError, api, type ClarifyingAnswer, type SafetyAssessment } from '../lib/api'
import { PROCESS_STEPS, ROUTES, isTradeId, loginUrl, requestUrl } from '../data/content'
import { useAuth } from '../state/AuthContext'
import { useIntake } from '../state/IntakeContext'
import type { TradeId } from '../types'

/*
  The Repair Intake screen (URL: /diagnose). Two steps:

  1. Describe   — trade, description, optional photos. "Continue" runs the SAFETY CHECK on the server
                  (no sign-in needed, so anyone in danger gets advice straight away).
  2. Safety     — shows the result before anything else:
                    high   → safety steps; AI diagnosis is not offered (the request can still be saved)
                    medium → clarifying questions; a professional is recommended
                    low    → continue
                  "Save and continue" saves the request (sign-in required) and opens it.
*/

type Step =
  | { kind: 'describe' }
  | { kind: 'checking' }
  | { kind: 'safety'; assessment: SafetyAssessment }

export default function DiagnosePage() {
  const { location, replace, navigate } = useRouter()
  const { status } = useAuth()
  const intake = useIntake()
  const { setTrade } = intake
  const tradeFromUrl = new URLSearchParams(location.search).get('trade')

  const [step, setStep] = useState<Step>({ kind: 'describe' })
  const [checkError, setCheckError] = useState<string | null>(null)
  const [answering, setAnswering] = useState(false)
  const [answerError, setAnswerError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const resultRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (tradeFromUrl === null) return
    if (isTradeId(tradeFromUrl)) setTrade(tradeFromUrl)
    replace(ROUTES.diagnose)
  }, [tradeFromUrl, setTrade, replace])

  // Bring the safety result into view (and to screen readers) when it appears.
  useEffect(() => {
    if (step.kind === 'safety') resultRef.current?.focus({ preventScroll: false })
  }, [step.kind])

  const keyFor = (values: { trade: TradeId; description: string }) => `${values.trade}|${values.description}`

  async function runCheck(values: { trade: TradeId; description: string }, answers: ClarifyingAnswer[]) {
    return api.assessSafety({ trade_id: values.trade, description: values.description, clarifying_answers: answers })
  }

  async function handleContinue(values: { trade: TradeId; description: string }) {
    setCheckError(null)
    setSaveError(null)
    setStep({ kind: 'checking' })
    try {
      // Answers only apply to the exact text they were given for (e.g. kept while signing in); any edit starts fresh.
      const key = keyFor(values)
      const answers = intake.safetyAnswersKey === key ? intake.safetyAnswers : []
      if (answers.length === 0) intake.setSafetyAnswers([], key)
      setStep({ kind: 'safety', assessment: await runCheck(values, answers) })
    } catch (err) {
      setCheckError(err instanceof ApiError ? err.message : 'Something went wrong. Please try again.')
      setStep({ kind: 'describe' })
    }
  }

  async function handleAnswers(newAnswers: ClarifyingAnswer[]) {
    if (!isTradeId(intake.values.trade)) return
    const merged = [...intake.safetyAnswers.filter((a) => !newAnswers.some((n) => n.question_id === a.question_id)), ...newAnswers]
    setAnswering(true)
    setAnswerError(null)
    try {
      const values = { trade: intake.values.trade, description: intake.values.description.trim() }
      const assessment = await runCheck(values, merged)
      intake.setSafetyAnswers(merged, keyFor(values))
      setStep({ kind: 'safety', assessment })
    } catch (err) {
      setAnswerError(err instanceof ApiError ? err.message : 'Something went wrong. Please try again.')
    } finally {
      setAnswering(false)
    }
  }

  async function handleSave() {
    if (!isTradeId(intake.values.trade)) return
    if (status !== 'signedIn') {
      navigate(loginUrl(ROUTES.diagnose, 'diagnose'))
      return
    }
    setSaving(true)
    setSaveError(null)
    try {
      const saved = await api.createRepairRequest({
        trade_id: intake.values.trade,
        description: intake.values.description.trim(),
        clarifying_answers: intake.safetyAnswers,
      })
      intake.setLastRequest(saved)
      // Upload the photos chosen during intake (best effort — they can be added again on the request page).
      for (const photo of intake.photos) {
        try {
          await api.uploadPhoto(saved.request_id, await fileToBase64(photo.file))
        } catch {
          /* shown as missing on the request page, where the person can add it again */
        }
      }
      intake.reset() // the draft is now saved on the server
      navigate(requestUrl(saved.request_id))
    } catch (err) {
      setSaveError(err instanceof ApiError ? err.message : 'Something went wrong. Please try again.')
      setSaving(false)
    }
  }

  const signedIn = status === 'signedIn'

  return (
    <PageContainer>
      <PageHeader
        title="Diagnose a Problem"
        documentTitle="Diagnose a Problem"
        intro="Tell us what needs fixing. We check it for safety first, then help you with the next step."
      />

      <ol className="mt-6 flex flex-wrap items-center gap-2 text-sm" aria-label="Progress">
        {[
          { n: 1, label: 'Describe', active: step.kind !== 'safety' },
          { n: 2, label: 'Safety check', active: step.kind === 'safety' },
          { n: 3, label: 'Diagnosis', active: false },
        ].map((s, i) => (
          <li key={s.n} className="flex items-center gap-2">
            {i > 0 && <span aria-hidden="true" className="h-px w-6 bg-navy-900/20" />}
            <span
              aria-current={s.active ? 'step' : undefined}
              className={`inline-flex items-center gap-2 rounded-full px-3 py-1 font-medium ${s.active ? 'bg-navy-900 text-white' : 'bg-white text-navy-700 ring-1 ring-navy-900/15'}`}
            >
              {s.n}. {s.label}
            </span>
          </li>
        ))}
      </ol>

      <div className="mt-6 grid grid-cols-1 gap-8 lg:grid-cols-[1fr_20rem] lg:items-start">
        <div>
          {step.kind === 'safety' ? (
            <div ref={resultRef} tabIndex={-1} className="space-y-5 focus:outline-none">
              <SafetyPanel
                assessment={step.assessment}
                onAnswer={(a) => void handleAnswers(a)}
                answering={answering}
                answerError={answerError}
              />

              <div className="rounded-2xl border border-navy-900/10 bg-white p-5 sm:p-6">
                {saveError && (
                  <div className="mb-4">
                    <Alert tone="error" announce title="Your request couldn’t be saved">
                      {saveError} What you typed is still here.
                    </Alert>
                  </div>
                )}
                {step.assessment.risk_level === 'high' ? (
                  <p className="text-sm leading-relaxed text-navy-700">
                    Your safety comes first. If you’d like a record of this problem — for example to show a professional — you can still save it.
                    {signedIn ? '' : ' You’ll need to sign in.'}
                  </p>
                ) : (
                  <p className="text-sm leading-relaxed text-navy-700">
                    {step.assessment.risk_level === 'medium'
                      ? 'You can save the request now and get an AI assessment that explains possible causes. Because of the possible risk, it won’t include do-it-yourself steps.'
                      : 'Next, save your request to get an AI diagnosis.'}
                    {signedIn ? '' : ' You’ll be asked to sign in or create an account; what you typed is kept.'}
                  </p>
                )}
                <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:flex-wrap">
                  <Button onClick={() => void handleSave()} disabled={saving} variant={step.assessment.risk_level === 'high' ? 'secondary' : 'primary'}>
                    {saving ? (
                      <>
                        <Spinner className="size-4" label="Saving" /> Saving…
                      </>
                    ) : step.assessment.risk_level === 'high' ? (
                      signedIn ? 'Save request (no diagnosis)' : 'Sign in to save request'
                    ) : signedIn ? (
                      <>
                        Save and continue <Icon name="arrowRight" className="size-4" />
                      </>
                    ) : (
                      <>
                        Sign in to continue <Icon name="arrowRight" className="size-4" />
                      </>
                    )}
                  </Button>
                  <Button variant="secondary" onClick={() => setStep({ kind: 'describe' })} disabled={saving}>
                    <Icon name="arrowLeft" className="size-4" />
                    Edit description
                  </Button>
                </div>
              </div>
            </div>
          ) : (
            <div className="rounded-2xl border border-navy-900/10 bg-white p-5 shadow-sm sm:p-8">
              <IntakeForm
                onValidSubmit={(values) => void handleContinue(values)}
                submitting={step.kind === 'checking'}
                submittingLabel="Checking safety…"
                footer={
                  checkError ? (
                    <Alert tone="error" announce title="The safety check couldn’t run">
                      {checkError} What you typed is still here.
                    </Alert>
                  ) : (
                    <Alert tone="info">
                      When you continue, MENDORA first runs an automatic safety check on your description — no sign-in needed.
                    </Alert>
                  )
                }
              />
            </div>
          )}
        </div>

        <aside className="space-y-5" aria-label="Before you start">
          <div className="rounded-2xl border border-red-700/20 bg-red-50 p-5 text-red-900">
            <h2 className="flex items-center gap-2 font-semibold">
              <Icon name="alert" className="size-5" />
              Is it dangerous right now?
            </h2>
            <p className="mt-2 text-sm leading-relaxed text-red-900/90">
              Don’t wait for a diagnosis. Move away from the danger and contact your local emergency service or a
              qualified professional if you notice:
            </p>
            <div className="mt-3">
              <DangerSignList variant="compact" />
            </div>
            <Link
              to={`${ROUTES.about}#emergency`}
              className="mt-4 inline-flex items-center gap-1 rounded text-sm font-semibold text-red-900 underline underline-offset-2 hover:text-red-950 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-red-700"
            >
              What to do in an emergency
              <Icon name="arrowRight" className="size-4" />
            </Link>
          </div>

          <div className="rounded-2xl border border-navy-900/10 bg-white p-5">
            <h2 className="font-semibold text-navy-900">What happens next</h2>
            <ol className="mt-3 space-y-3">
              {PROCESS_STEPS.map((s, index) => (
                <li key={s.title} className="flex gap-3 text-sm">
                  <span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-navy-900 text-xs font-bold text-white">
                    {index + 1}
                  </span>
                  <span className="text-navy-700">{s.title}</span>
                </li>
              ))}
            </ol>
          </div>
        </aside>
      </div>
    </PageContainer>
  )
}
