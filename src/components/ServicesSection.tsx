import { useState } from 'react'
import Section from './Section'
import ServiceCard from './ServiceCard'
import Button from './Button'
import Icon from './Icon'
import { TRADES, diagnoseUrl, getTrade } from '../data/content'
import type { TradeId } from '../types'

export default function ServicesSection() {
  // Which card is selected (null = none). Clicking the selected card again un-selects it.
  const [selected, setSelected] = useState<TradeId | null>(null)
  const selectedTrade = selected ? getTrade(selected) : null

  return (
    <Section
      id="services"
      eyebrow="Services"
      title="Three trades, one place to start"
      intro="MENDORA focuses on the repairs homes need most. Select a service to begin a repair request for it."
    >
      <div className="grid gap-5 md:grid-cols-3">
        {TRADES.map((trade) => (
          <ServiceCard
            key={trade.id}
            trade={trade}
            selected={selected === trade.id}
            onSelect={() => setSelected((current) => (current === trade.id ? null : trade.id))}
          />
        ))}
      </div>

      {/* aria-live announces the change to screen-reader users when a card is selected */}
      <div
        aria-live="polite"
        className="mt-6 flex min-h-[4.5rem] flex-col items-start justify-between gap-4 rounded-2xl border border-navy-900/10 bg-white p-4 sm:flex-row sm:items-center sm:px-6"
      >
        {selectedTrade ? (
          <>
            <p className="flex items-center gap-2 text-navy-800">
              <Icon name="checkCircle" className="size-5 text-teal-700" />
              <span>
                <strong className="font-semibold">{selectedTrade.name}</strong> selected.
              </span>
            </p>
            <Button to={diagnoseUrl(selectedTrade.id)}>
              Diagnose a {selectedTrade.name.toLowerCase()} problem
              <Icon name="arrowRight" className="size-4" />
            </Button>
          </>
        ) : (
          <p className="text-navy-600">Select a service above to start a diagnosis for it.</p>
        )}
      </div>
    </Section>
  )
}
