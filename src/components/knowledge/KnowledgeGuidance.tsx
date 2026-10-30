import { useEffect, useState } from 'react'
import Alert from '../Alert'
import Badge from '../Badge'
import Button from '../Button'
import Icon from '../Icon'
import Spinner from '../Spinner'
import { ApiError, api, type KnowledgeGuidance as Guidance } from '../../lib/api'

/*
  Matching repair-guide entries from MENDORA's knowledge base (Step 7).
  The SERVER runs the safety check first and decides what may be shown:
    - high risk   → nothing (the safety advice above is all that applies)
    - medium risk → possible causes only, no do-it-yourself steps
    - low risk    → possible causes and simple, safe checks
  This component only displays what the server returned.
*/

interface Props {
  requestId: string
  /** Changes whenever the safety result changes, so the guidance is reloaded. */
  safetyKey: string
}

export default function KnowledgeGuidance({ requestId, safetyKey }: Props) {
  const [data, setData] = useState<Guidance | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [reload, setReload] = useState(0)

  useEffect(() => {
    let cancelled = false
    setError(null)
    api
      .getGuidance(requestId)
      .then((g) => !cancelled && setData(g))
      .catch((err) => !cancelled && setError(err instanceof ApiError ? err : new ApiError(0, 'unknown', 'Something went wrong.')))
    return () => {
      cancelled = true
    }
  }, [requestId, safetyKey, reload])

  if (error) {
    return (
      <Alert
        tone="warning"
        title="Repair guides couldn’t be loaded"
        action={
          <Button variant="secondary" onClick={() => setReload((n) => n + 1)}>
            Try again
          </Button>
        }
      >
        {error.message}
      </Alert>
    )
  }

  if (!data) {
    return (
      <div className="flex items-center gap-3 rounded-2xl border border-navy-900/10 bg-white p-5 text-navy-700" role="status">
        <Spinner /> Looking for matching repair guides…
      </div>
    )
  }

  // High risk: the server returns nothing to show. The safety panel already says what to do.
  if (data.status === 'blocked_by_safety') return null

  return (
    <section aria-labelledby="guides-heading" className="rounded-2xl border border-navy-900/10 bg-white p-5 sm:p-6">
      <div className="flex flex-wrap items-center gap-3">
        <h2 id="guides-heading" className="text-xl font-semibold text-navy-900">
          Matching repair guides
        </h2>
        {data.mode === 'professional_only' && (
          <Badge tone="amber" icon="shield">
            Professional-only
          </Badge>
        )}
      </div>
      <p className="mt-2 text-sm leading-relaxed text-navy-700">{data.message}</p>

      {data.matches.length > 0 && (
        <ul className="mt-5 space-y-4">
          {data.matches.map(({ entry, relevance, matched_terms }) => (
            <li key={entry.id} className="rounded-xl border border-navy-900/10 p-4 sm:p-5">
              <div className="flex flex-wrap items-center gap-2">
                <h3 className="font-semibold text-navy-900">{entry.title}</h3>
                <Badge tone="navy">{Math.round(relevance * 100)}% word match</Badge>
                {entry.source.verification_status === 'unverified' && <Badge tone="amber">Not professionally reviewed</Badge>}
              </div>
              <p className="mt-1 text-xs text-navy-600">Matched words: {matched_terms.join(', ')}</p>

              <h4 className="mt-4 text-sm font-semibold text-navy-900">Possible causes (not a diagnosis)</h4>
              <ul className="mt-2 space-y-2 text-sm text-navy-700">
                {entry.possible_causes.map((c) => (
                  <li key={c.title}>
                    <span className="font-medium text-navy-900">Possibly: {c.title}.</span> {c.explanation}
                  </li>
                ))}
              </ul>

              {entry.clarifying_questions.length > 0 && (
                <>
                  <h4 className="mt-4 text-sm font-semibold text-navy-900">Questions worth asking yourself</h4>
                  <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-navy-700">
                    {entry.clarifying_questions.map((q) => (
                      <li key={q}>{q}</li>
                    ))}
                  </ul>
                </>
              )}

              {entry.steps_shown && entry.next_steps.length > 0 ? (
                <>
                  <h4 className="mt-4 text-sm font-semibold text-navy-900">Simple, safe checks</h4>
                  <ol className="mt-2 list-decimal space-y-1 pl-5 text-sm text-navy-700">
                    {entry.next_steps.map((s) => (
                      <li key={s}>{s}</li>
                    ))}
                  </ol>
                </>
              ) : (
                entry.steps_note && (
                  <p className="mt-4 flex items-start gap-2 text-sm text-navy-700">
                    <Icon name="shield" className="mt-0.5 size-4 shrink-0 text-amber-700" />
                    {entry.steps_note}
                  </p>
                )
              )}

              {entry.safety_restrictions.length > 0 && (
                <ul className="mt-4 space-y-1 text-sm text-red-900">
                  {entry.safety_restrictions.map((r) => (
                    <li key={r} className="flex items-start gap-2">
                      <Icon name="alert" className="mt-0.5 size-4 shrink-0 text-red-700" />
                      {r}
                    </li>
                  ))}
                </ul>
              )}

              {entry.professional_recommended && (
                <p className="mt-4 rounded-lg bg-navy-50 p-3 text-sm text-navy-800">
                  <span className="font-semibold">A professional is recommended.</span> {entry.professional_reason}
                </p>
              )}
              <p className="mt-3 text-xs text-navy-600">Source: {entry.source.note}</p>
            </li>
          ))}
        </ul>
      )}

      {data.similar_verified_cases.length > 0 && (
        <div className="mt-6">
          <h3 className="font-semibold text-navy-900">Similar repairs confirmed by technicians</h3>
          <p className="mt-1 text-xs text-navy-600">Anonymised past cases that an admin checked. Your problem may be different.</p>
          <ul className="mt-3 space-y-2">
            {data.similar_verified_cases.map((c) => (
              <li key={c.case_id} className="rounded-lg border border-navy-900/10 p-3 text-sm text-navy-700">
                <span className="font-medium text-navy-900">{c.confirmed_cause}</span> — {c.symptoms_summary}
                {c.completion_minutes != null && ` · about ${c.completion_minutes} min`}
                {c.cost_amount != null && ` · ${c.currency ?? ''} ${c.cost_amount}`}
              </li>
            ))}
          </ul>
        </div>
      )}

      <p className="mt-5 text-xs leading-relaxed text-navy-600">{data.disclaimer}</p>
    </section>
  )
}
