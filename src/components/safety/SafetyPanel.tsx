import { useState, type FormEvent, type ReactNode } from 'react'
import Badge from '../Badge'
import Button from '../Button'
import Icon from '../Icon'
import Spinner from '../Spinner'
import { Link } from '../../lib/router'
import { ROUTES } from '../../data/content'
import type { ClarifyingAnswer, SafetyAnswer, SafetyAssessment } from '../../lib/api'

/*
  Shows the backend's safety decision. It is always shown BEFORE any AI diagnosis or repair advice.

  high   → red, prominent: what to do now, numbered safety steps. AI diagnosis and DIY are switched off.
  medium → amber: why it may be risky, a professional is recommended, and yes/no/not-sure questions.
  low    → green: no immediate danger found; the user may continue.

  The frontend never decides the risk itself — it only displays what the server returned.
*/

interface SafetyPanelProps {
  assessment: SafetyAssessment
  /** Medium risk: called with the user's answers to the clarifying questions. */
  onAnswer?: (answers: ClarifyingAnswer[]) => void
  answering?: boolean
  answerError?: string | null
  /** Extra content at the bottom (e.g. the next-step buttons). */
  children?: ReactNode
}

const ANSWER_LABELS: Record<SafetyAnswer, string> = { yes: 'Yes', no: 'No', not_sure: 'Not sure' }

export default function SafetyPanel({ assessment, onAnswer, answering = false, answerError, children }: SafetyPanelProps) {
  const level = assessment.risk_level
  const styles = {
    high: { box: 'border-2 border-red-700 bg-red-50', title: 'Stop — this may be dangerous', badge: 'High risk', tone: 'red', icon: 'alert' },
    medium: { box: 'border-2 border-amber-500 bg-amber-50', title: 'Check needed before any repair', badge: 'Medium risk', tone: 'amber', icon: 'shield' },
    low: { box: 'border border-teal-700/30 bg-teal-50', title: 'No immediate danger found', badge: 'Low risk', tone: 'teal', icon: 'checkCircle' },
  } as const
  const s = styles[level]

  return (
    <section
      aria-labelledby="safety-heading"
      data-risk={level}
      role={level === 'high' ? 'alert' : undefined}
      className={`rounded-2xl p-5 sm:p-6 ${s.box}`}
    >
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <h2 id="safety-heading" className={`flex items-center gap-2 text-xl font-bold ${level === 'high' ? 'text-red-950' : 'text-navy-900'}`}>
          <Icon name={s.icon} className={`size-6 ${level === 'high' ? 'text-red-700' : level === 'medium' ? 'text-amber-700' : 'text-teal-700'}`} />
          {s.title}
        </h2>
        <Badge tone={s.tone} icon="shield">
          Safety check: {s.badge}
        </Badge>
      </div>

      <p className={`mt-3 leading-relaxed ${level === 'high' ? 'text-red-950' : 'text-navy-800'}`}>{assessment.safety_message}</p>

      <div className={`mt-4 rounded-xl p-4 ${level === 'high' ? 'bg-white ring-1 ring-red-700/30' : 'bg-white/80 ring-1 ring-navy-900/10'}`}>
        <p className="text-sm font-semibold text-navy-900">{level === 'high' ? 'What to do now' : 'Recommended next step'}</p>
        <p className="mt-1 leading-relaxed text-navy-900">{assessment.recommended_action}</p>
      </div>

      {assessment.emergency_steps.length > 0 && (
        <ol className="mt-4 space-y-2.5">
          {assessment.emergency_steps.map((step, i) => (
            <li key={step} className="flex gap-3 leading-relaxed text-red-950">
              <span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-red-700 text-xs font-bold text-white">{i + 1}</span>
              {step}
            </li>
          ))}
        </ol>
      )}

      {assessment.matched_hazards.length > 0 && (
        <div className="mt-5">
          <p className="text-sm font-semibold text-navy-900">What the safety check noticed</p>
          <ul className="mt-2 flex flex-wrap gap-2">
            {assessment.matched_hazards.map((h) => (
              <li key={h.id}>
                <span
                  className={`inline-flex flex-wrap items-center gap-1 rounded-lg px-2.5 py-1 text-sm ring-1 ring-inset ${
                    h.risk === 'high' ? 'bg-white text-red-900 ring-red-700/30' : 'bg-white text-amber-900 ring-amber-700/30'
                  }`}
                >
                  <span className="font-semibold">{h.label}</span>
                  {h.matched_text && <span className="text-navy-600">— you wrote “{h.matched_text}”</span>}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {level === 'high' && (
        <p className="mt-5 flex items-start gap-2 rounded-lg bg-white/70 p-3 text-sm font-medium text-red-950 ring-1 ring-red-700/20">
          <Icon name="lock" className="mt-0.5 size-4 shrink-0" />
          AI diagnosis and do-it-yourself repair steps are switched off for this problem, for your safety.
        </p>
      )}

      {level === 'medium' && assessment.clarifying_questions.length > 0 && onAnswer && (
        <ClarifyingQuestions key={assessment.clarifying_questions.map((q) => q.id).join()} assessment={assessment} onAnswer={onAnswer} busy={answering} error={answerError} />
      )}

      {assessment.answered_questions.length > 0 && (
        <details className="mt-4 text-sm text-navy-700">
          <summary className="cursor-pointer font-medium text-navy-800">Your answers ({assessment.answered_questions.length})</summary>
          <ul className="mt-2 space-y-1">
            {assessment.answered_questions.map((a) => (
              <li key={a.id}>
                {a.text} <strong className="text-navy-900">{ANSWER_LABELS[a.answer]}</strong>
              </li>
            ))}
          </ul>
        </details>
      )}
      {assessment.resolved_hazards.length > 0 && level !== 'high' && (
        <p className="mt-3 text-sm text-navy-700">Cleared by your answers: {assessment.resolved_hazards.join(', ')}.</p>
      )}

      {children && <div className="mt-5">{children}</div>}

      <p className="mt-5 flex items-start gap-2 text-xs leading-relaxed text-navy-600">
        <Icon name="info" className="mt-px size-3.5 shrink-0" />
        <span>
          {assessment.disclaimer}{' '}
          <Link to={`${ROUTES.about}#emergency`} className="rounded font-medium underline underline-offset-2 focus-visible:outline-2 focus-visible:outline-teal-600">
            Emergency guidance
          </Link>
        </span>
      </p>
    </section>
  )
}

function ClarifyingQuestions({
  assessment,
  onAnswer,
  busy,
  error,
}: {
  assessment: SafetyAssessment
  onAnswer: (answers: ClarifyingAnswer[]) => void
  busy: boolean
  error?: string | null
}) {
  const [answers, setAnswers] = useState<Record<string, SafetyAnswer>>({})
  const [localError, setLocalError] = useState<string | null>(null)

  function submit(event: FormEvent) {
    event.preventDefault()
    const list = Object.entries(answers).map(([question_id, answer]) => ({ question_id, answer }))
    if (list.length === 0) {
      setLocalError('Please answer at least one question.')
      return
    }
    setLocalError(null)
    onAnswer(list)
  }

  const shownError = localError ?? error
  return (
    <form onSubmit={submit} noValidate className="mt-5 rounded-xl bg-white p-4 ring-1 ring-navy-900/10 sm:p-5">
      <h3 className="font-semibold text-navy-900">A few safety questions</h3>
      <p className="mt-1 text-sm text-navy-600">Your answers help decide whether this is safe to look into further. If in doubt, choose “Not sure”.</p>
      <div className="mt-4 space-y-5">
        {assessment.clarifying_questions.map((q) => (
          <fieldset key={q.id}>
            <legend className="text-sm font-medium leading-relaxed text-navy-900">{q.text}</legend>
            <div className="mt-2 flex flex-wrap gap-2">
              {q.options.map((option) => {
                const checked = answers[q.id] === option
                return (
                  <label
                    key={option}
                    className={`inline-flex h-11 cursor-pointer items-center rounded-lg px-4 text-sm font-semibold ring-1 ring-inset transition-colors has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-teal-600 ${
                      checked ? 'bg-navy-900 text-white ring-navy-900' : 'bg-white text-navy-900 ring-navy-900/20 hover:bg-navy-50'
                    }`}
                  >
                    <input
                      type="radio"
                      name={`safety-${q.id}`}
                      value={option}
                      checked={checked}
                      onChange={() => setAnswers((a) => ({ ...a, [q.id]: option }))}
                      className="sr-only"
                    />
                    {ANSWER_LABELS[option]}
                  </label>
                )
              })}
            </div>
          </fieldset>
        ))}
      </div>
      {shownError && (
        <p role="alert" className="mt-4 flex items-start gap-1.5 text-sm text-red-700">
          <Icon name="alert" className="mt-0.5 size-4 shrink-0" />
          {shownError}
        </p>
      )}
      <Button type="submit" variant="secondary" className="mt-4" disabled={busy}>
        {busy ? (
          <>
            <Spinner className="size-4" label="Checking" /> Checking…
          </>
        ) : (
          'Update safety check'
        )}
      </Button>
    </form>
  )
}
