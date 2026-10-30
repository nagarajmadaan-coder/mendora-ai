import { useState, type FormEvent } from 'react'
import Badge from '../Badge'
import Button from '../Button'
import Icon from '../Icon'
import Spinner from '../Spinner'
import type { Diagnosis, FollowUpAnswer } from '../../lib/api'

/*
  Shows a stored AI diagnosis. It is only ever rendered BELOW the safety result, and never for
  high-risk requests (the server doesn't return a diagnosis for those).

  safety_mode "professional_only" (medium risk): possible causes are explained, but there are no
  DIY steps — the next step is always a professional.
*/

interface DiagnosisCardProps {
  diagnosis: Diagnosis
  /** Called when the user answers follow-up questions and asks for an updated diagnosis. */
  onAnswer?: (answers: FollowUpAnswer[]) => void
  busy?: boolean
}

export default function DiagnosisCard(props: DiagnosisCardProps) {
  return <AiResult {...props} />
}

function AiResult({ diagnosis, onAnswer, busy }: DiagnosisCardProps) {
  const [answers, setAnswers] = useState<string[]>(() => diagnosis.follow_up_questions.map(() => ''))
  const [answerError, setAnswerError] = useState<string | null>(null)

  function submitAnswers(event: FormEvent) {
    event.preventDefault()
    const filled: FollowUpAnswer[] = diagnosis.follow_up_questions
      .map((question, i) => ({ question, answer: answers[i]?.trim() ?? '' }))
      .filter((qa) => qa.answer)
    if (filled.length === 0) {
      setAnswerError('Please answer at least one question.')
      return
    }
    setAnswerError(null)
    onAnswer?.(filled)
  }

  return (
    <section aria-labelledby="diagnosis-heading" className="space-y-6">
      <div className="flex flex-wrap items-center gap-2">
        <h2 id="diagnosis-heading" className="text-xl font-semibold text-navy-900">
          AI assessment
        </h2>
        {diagnosis.trial ? (
          <Badge tone="amber" icon="info">
            Trial — web search summary
          </Badge>
        ) : (
          <Badge tone="teal" icon="sparkles">
            AI-generated
          </Badge>
        )}
        <Badge tone="amber">Possibilities, not confirmed</Badge>
        {diagnosis.safety_mode === 'professional_only' && (
          <Badge tone="amber" icon="shield">
            Professional-only — no DIY steps
          </Badge>
        )}
      </div>

      {diagnosis.safety_mode === 'professional_only' && (
        <p className="flex items-start gap-2 rounded-xl border border-amber-600/25 bg-amber-50 p-3 text-sm leading-relaxed text-navy-800">
          <Icon name="shield" className="mt-0.5 size-4 shrink-0 text-amber-700" />
          Because the safety check found a possible risk, this assessment only explains what might be wrong. It doesn’t include do-it-yourself repair steps.
        </p>
      )}
      {diagnosis.safety_filter_applied && (
        <p className="flex items-start gap-2 rounded-xl border border-navy-900/10 bg-navy-50 p-3 text-sm leading-relaxed text-navy-800">
          <Icon name="info" className="mt-0.5 size-4 shrink-0 text-navy-700" />
          MENDORA removed part of the AI’s answer because it suggested work that isn’t safe to do yourself.
        </p>
      )}

      {diagnosis.trial && (
        <p className="flex items-start gap-2 rounded-xl border border-amber-600/25 bg-amber-50 p-3 text-sm leading-relaxed text-navy-800">
          <Icon name="info" className="mt-0.5 size-4 shrink-0 text-amber-700" />
          Trial mode: this summary comes from a Tavily web search, not a full AI diagnosis. It doesn’t list causes or ask
          follow-up questions.
        </p>
      )}

      <div>
        <h3 className="text-sm font-semibold tracking-wide text-navy-600 uppercase">Summary</h3>
        <p className="mt-2 leading-relaxed text-navy-900">{diagnosis.summary}</p>
      </div>

      {diagnosis.possible_causes.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold tracking-wide text-navy-600 uppercase">Possible causes</h3>
          <ol className="mt-3 space-y-3">
            {diagnosis.possible_causes.map((cause, i) => (
              <li key={`${cause.title}-${i}`} className="rounded-xl border border-navy-900/10 bg-canvas p-4">
                <p className="text-xs font-semibold text-amber-800">Possibility {i + 1}</p>
                <p className="mt-0.5 font-semibold text-navy-900">{cause.title}</p>
                <p className="mt-1 text-sm leading-relaxed text-navy-700">{cause.explanation}</p>
              </li>
            ))}
          </ol>
        </div>
      )}

      {diagnosis.sources && diagnosis.sources.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold tracking-wide text-navy-600 uppercase">Web pages used</h3>
          <ul className="mt-2 space-y-1.5 text-sm">
            {diagnosis.sources.map((s) => (
              <li key={s.url} className="min-w-0">
                <a href={s.url} target="_blank" rel="noopener noreferrer nofollow" className="break-words text-teal-800 underline">
                  {s.title}
                </a>{' '}
                <span className="text-navy-600">({s.domain})</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="rounded-xl border border-teal-700/20 bg-teal-50 p-4">
        <h3 className="flex items-center gap-2 font-semibold text-navy-900">
          <Icon name="arrowRight" className="size-4 text-teal-700" />
          Recommended next step
        </h3>
        <p className="mt-1 leading-relaxed text-navy-800">{diagnosis.recommended_next_step}</p>
      </div>

      <div
        className={`flex items-start gap-3 rounded-xl border p-4 ${
          diagnosis.professional_recommended ? 'border-amber-600/30 bg-amber-50' : 'border-navy-900/10 bg-white'
        }`}
      >
        <Icon name={diagnosis.professional_recommended ? 'phone' : 'check'} className="mt-0.5 size-5 shrink-0 text-navy-700" />
        <div>
          <p className="font-semibold text-navy-900">
            {diagnosis.professional_recommended ? 'A professional is recommended' : 'A professional may not be needed yet'}
          </p>
          {diagnosis.professional_reason && <p className="mt-1 text-sm leading-relaxed text-navy-700">{diagnosis.professional_reason}</p>}
        </div>
      </div>

      {diagnosis.follow_up_questions.length > 0 && onAnswer && (
        <form onSubmit={submitAnswers} noValidate className="rounded-xl border border-navy-900/10 bg-white p-4 sm:p-5">
          <h3 className="font-semibold text-navy-900">Help narrow it down</h3>
          <p className="mt-1 text-sm text-navy-600">Answer any of these questions to get an updated assessment.</p>
          <div className="mt-4 space-y-4">
            {diagnosis.follow_up_questions.map((question, i) => (
              <div key={question}>
                <label htmlFor={`followup-${i}`} className="block text-sm font-medium text-navy-900">
                  {question}
                </label>
                <input
                  id={`followup-${i}`}
                  value={answers[i] ?? ''}
                  maxLength={500}
                  onChange={(e) => setAnswers((a) => a.map((v, j) => (j === i ? e.target.value : v)))}
                  className="mt-2 block h-11 w-full rounded-lg border border-navy-900/20 bg-white px-3 text-base text-navy-900 focus:border-teal-600 focus:outline-2 focus:outline-offset-0 focus:outline-teal-600"
                />
              </div>
            ))}
          </div>
          {answerError && (
            <p role="alert" className="mt-3 flex items-center gap-1.5 text-sm text-red-700">
              <Icon name="alert" className="size-4" />
              {answerError}
            </p>
          )}
          <Button type="submit" variant="secondary" className="mt-4" disabled={busy}>
            {busy ? (
              <>
                <Spinner className="size-4" label="Updating" /> Updating…
              </>
            ) : (
              'Update assessment'
            )}
          </Button>
        </form>
      )}

      <p className="flex items-start gap-2 border-t border-navy-900/10 pt-4 text-sm leading-relaxed text-navy-600">
        <Icon name="info" className="mt-0.5 size-4 shrink-0" />
        <span>
          {diagnosis.disclaimer}
          {diagnosis.model && <span className="block text-xs text-navy-600/80">Generated by {diagnosis.model}.</span>}
        </span>
      </p>
    </section>
  )
}
