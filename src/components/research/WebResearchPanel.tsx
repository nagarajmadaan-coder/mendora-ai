import { useState } from 'react'
import Alert from '../Alert'
import Badge from '../Badge'
import Button from '../Button'
import Icon from '../Icon'
import Spinner from '../Spinner'
import { ApiError, api, type WebResearch } from '../../lib/api'

/*
  AI web research (Tavily): an AI summary of public web pages about the problem, plus the sources.
  It is NOT the AI diagnosis. The server re-checks safety first:
    medium risk → links only; high risk → nothing (this panel isn't shown, and the server refuses anyway).
*/

export default function WebResearchPanel({ requestId }: { requestId: string }) {
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<WebResearch | null>(null)
  const [error, setError] = useState<ApiError | null>(null)

  const run = async () => {
    if (busy) return
    setBusy(true)
    setError(null)
    try {
      setResult(await api.webResearch(requestId))
    } catch (err) {
      setError(err instanceof ApiError ? err : new ApiError(0, 'unknown', 'Something went wrong.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section aria-labelledby="web-heading" className="rounded-2xl border border-navy-900/10 bg-white p-5 sm:p-6" aria-live="polite">
      <div className="flex flex-wrap items-center gap-3">
        <h2 id="web-heading" className="text-xl font-semibold text-navy-900">
          AI web research
        </h2>
        <Badge tone="navy" icon="search">
          Tavily · not a diagnosis
        </Badge>
      </div>
      <p className="mt-2 text-sm leading-relaxed text-navy-700">
        Searches the web for your problem and shows an AI summary of what it found, with the sources. Only the trade and your
        description are sent (emails and phone numbers removed).
      </p>

      {!result && !error && (
        <Button className="mt-4" onClick={() => void run()} disabled={busy}>
          {busy ? <Spinner /> : <Icon name="search" className="size-4" />}
          {busy ? 'Searching the web…' : 'Search the web with AI'}
        </Button>
      )}

      {error && (
        <div className="mt-4">
          <Alert
            tone={error.code === 'web_research_not_configured' ? 'warning' : 'error'}
            announce
            title={error.code === 'web_research_not_configured' ? 'AI web research isn’t set up yet' : 'Web research didn’t work'}
            action={
              error.code !== 'web_research_not_configured' && error.code !== 'blocked_by_safety' ? (
                <Button variant="secondary" onClick={() => void run()} disabled={busy}>
                  Try again
                </Button>
              ) : undefined
            }
          >
            {error.message}
          </Alert>
        </div>
      )}

      {result && (
        <div className="mt-4 space-y-4">
          {result.answer && (
            <div className="rounded-xl bg-navy-50 p-4">
              <p className="text-xs font-semibold tracking-wide text-navy-600 uppercase">AI summary of web pages</p>
              <p className="mt-1 leading-relaxed text-navy-900">{result.answer}</p>
            </div>
          )}
          {result.answer_note && (
            <p className="flex items-start gap-2 text-sm text-navy-700">
              <Icon name={result.mode === 'sources_only' ? 'shield' : 'info'} className="mt-0.5 size-4 shrink-0" />
              {result.answer_note}
            </p>
          )}
          {result.sources.length > 0 ? (
            <div>
              <h3 className="text-sm font-semibold text-navy-900">Sources</h3>
              <ul className="mt-2 space-y-2">
                {result.sources.map((s) => (
                  <li key={s.url} className="rounded-lg border border-navy-900/10 p-3 text-sm">
                    <a href={s.url} target="_blank" rel="noopener noreferrer nofollow" className="font-medium break-words text-teal-800 hover:underline">
                      {s.title}
                    </a>
                    <span className="block text-xs text-navy-600">{s.domain} · opens in a new tab</span>
                    {s.snippet && <span className="mt-1 block text-navy-700">{s.snippet}</span>}
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <p className="text-sm text-navy-700">No web pages were found for this search.</p>
          )}
          <p className="text-xs leading-relaxed text-navy-600">{result.disclaimer}</p>
          <p className="text-xs break-words text-navy-600">Sent to Tavily: “{result.query_sent}”</p>
        </div>
      )}
    </section>
  )
}
