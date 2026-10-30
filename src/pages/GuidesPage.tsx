import { useEffect, useMemo, useState } from 'react'
import PageHeader, { PageContainer } from '../components/PageHeader'
import Alert from '../components/Alert'
import Badge from '../components/Badge'
import Button from '../components/Button'
import Icon from '../components/Icon'
import Spinner from '../components/Spinner'
import { ApiError, api, type KnowledgeEntry } from '../lib/api'
import { ROUTES, TRADES, diagnoseUrl } from '../data/content'
import type { TradeId } from '../types'

/*
  Repair guides (URL: /guides) — merged feature: browse MENDORA's knowledge base.
  Browsing shows possible causes, warnings and when to call a professional — never the DIY steps.
  Steps appear only after the safety check, on your own saved request.
*/

type Summary = { id: string; trade: TradeId; category: string; title: string; symptoms: string[]; professional_recommended: boolean; source: KnowledgeEntry['source'] }
type Detail = Omit<KnowledgeEntry, 'next_steps' | 'steps_shown' | 'steps_note'>

export default function GuidesPage() {
  const [entries, setEntries] = useState<Summary[] | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [trade, setTrade] = useState<TradeId | ''>('')
  const [q, setQ] = useState('')
  const [open, setOpen] = useState<string | null>(null)
  const [detail, setDetail] = useState<Record<string, Detail>>({})

  useEffect(() => {
    api
      .listKnowledge()
      .then((r) => setEntries(r.entries as Summary[]))
      .catch((err) => setError(err instanceof ApiError ? err : new ApiError(0, 'unknown', 'Something went wrong.')))
  }, [])

  const shown = useMemo(() => {
    const words = q.toLowerCase().split(/\s+/).filter(Boolean)
    return (entries ?? []).filter(
      (e) => (!trade || e.trade === trade) && words.every((w) => `${e.title} ${e.category} ${e.symptoms.join(' ')}`.toLowerCase().includes(w)),
    )
  }, [entries, trade, q])

  const toggle = async (id: string) => {
    setOpen((cur) => (cur === id ? null : id))
    if (!detail[id]) {
      try {
        const d = await api.getKnowledgeEntry(id)
        setDetail((m) => ({ ...m, [id]: d }))
      } catch {
        /* the summary is still shown */
      }
    }
  }

  return (
    <PageContainer>
      <PageHeader
        title="Repair guides"
        documentTitle="Repair guides"
        intro="Common plumbing, electrical and carpentry problems: what usually causes them, and when to call a professional. Simple checks are shown only after a safety check on your own problem."
      />
      <div className="mt-6 flex flex-col gap-3 sm:flex-row">
        <select
          value={trade}
          onChange={(e) => setTrade(e.target.value as TradeId | '')}
          aria-label="Trade"
          className="h-11 rounded-xl border border-navy-900/20 bg-white px-3 text-base text-navy-900 focus:border-teal-600 focus:outline-2 focus:outline-teal-600"
        >
          <option value="">All trades</option>
          {TRADES.map((t) => (
            <option key={t.id} value={t.id}>
              {t.name}
            </option>
          ))}
        </select>
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search, e.g. dripping tap"
          aria-label="Search guides"
          className="h-11 flex-1 rounded-xl border border-navy-900/20 bg-white px-4 text-base text-navy-900 placeholder:text-navy-600/70 focus:border-teal-600 focus:outline-2 focus:outline-teal-600"
        />
      </div>
      <p className="mt-3 text-xs text-navy-600">
        Written by the MENDORA team and <strong>not reviewed by a licensed professional</strong>. Causes are possibilities, not a diagnosis.
      </p>

      <div className="mt-5">
        {error ? (
          <Alert tone="error" title="Guides couldn’t be loaded">
            {error.message}
          </Alert>
        ) : !entries ? (
          <div className="flex items-center gap-3 text-navy-700" role="status">
            <Spinner /> Loading guides…
          </div>
        ) : shown.length === 0 ? (
          <p className="rounded-2xl border border-dashed border-navy-900/20 bg-white p-8 text-center text-navy-700">No guides match. Try other words, or describe your problem for a safety check.</p>
        ) : (
          <ul className="space-y-3">
            {shown.map((e) => {
              const d = detail[e.id]
              const isOpen = open === e.id
              const tradeInfo = TRADES.find((t) => t.id === e.trade)
              return (
                <li key={e.id} className="rounded-2xl border border-navy-900/10 bg-white">
                  <button
                    type="button"
                    aria-expanded={isOpen}
                    onClick={() => void toggle(e.id)}
                    className="flex w-full items-start gap-3 p-4 text-left focus-visible:outline-2 focus-visible:outline-teal-600 sm:p-5"
                  >
                    <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-navy-900 text-teal-300">
                      <Icon name={tradeInfo?.icon ?? 'home'} className="size-5" />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="flex flex-wrap items-center gap-2">
                        <span className="font-semibold text-navy-900">{e.title}</span>
                        {e.professional_recommended && <Badge tone="amber">Professional recommended</Badge>}
                      </span>
                      <span className="mt-1 block text-sm text-navy-600">{e.symptoms.slice(0, 2).join(' · ')}</span>
                    </span>
                    <Icon name="arrowRight" className={`mt-1 size-5 shrink-0 text-navy-600 transition-transform ${isOpen ? 'rotate-90' : ''}`} />
                  </button>
                  {isOpen && (
                    <div className="border-t border-navy-900/10 px-4 pt-3 pb-5 text-sm sm:px-5">
                      {!d ? (
                        <Spinner />
                      ) : (
                        <>
                          <h3 className="font-semibold text-navy-900">Possible causes (not a diagnosis)</h3>
                          <ul className="mt-1 space-y-1 text-navy-700">
                            {d.possible_causes.map((c) => (
                              <li key={c.title}>
                                <span className="font-medium text-navy-900">Possibly: {c.title}.</span> {c.explanation}
                              </li>
                            ))}
                          </ul>
                          {d.safety_restrictions.length > 0 && (
                            <ul className="mt-3 space-y-1 text-red-900">
                              {d.safety_restrictions.map((r) => (
                                <li key={r} className="flex items-start gap-2">
                                  <Icon name="alert" className="mt-0.5 size-4 shrink-0 text-red-700" />
                                  {r}
                                </li>
                              ))}
                            </ul>
                          )}
                          {d.professional_reason && <p className="mt-3 rounded-lg bg-navy-50 p-3 text-navy-800">{d.professional_reason}</p>}
                          <div className="mt-4 flex flex-wrap items-center gap-3">
                            <Button to={diagnoseUrl(e.trade)}>Check my problem</Button>
                            <span className="text-xs text-navy-600">Simple safe checks appear after the safety check on your own request.</span>
                          </div>
                        </>
                      )}
                    </div>
                  )}
                </li>
              )
            })}
          </ul>
        )}
      </div>
      <p className="mt-8 text-sm text-navy-700">
        Something dangerous? Sparks, gas smell, flooding or cracking structures: leave the area and call emergency services.{' '}
        <a className="text-teal-800 underline" href={`${ROUTES.about}#emergency`}>
          Emergency guidance
        </a>
      </p>
    </PageContainer>
  )
}
