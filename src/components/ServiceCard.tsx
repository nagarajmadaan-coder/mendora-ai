import Icon from './Icon'
import type { Trade } from '../types'

interface ServiceCardProps {
  trade: Trade
  selected: boolean
  onSelect: () => void
}

/*
  A clickable card. It is a real <button> so it works with keyboard (Tab + Enter/Space)
  and screen readers. `aria-pressed` tells assistive tech whether it is selected.
*/
export default function ServiceCard({ trade, selected, onSelect }: ServiceCardProps) {
  return (
    <button
      type="button"
      aria-pressed={selected}
      onClick={onSelect}
      className={`group relative flex h-full w-full flex-col rounded-2xl border bg-white p-6 text-left transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-600 ${
        selected
          ? 'border-teal-600 ring-2 ring-teal-600/25'
          : 'border-navy-900/10 hover:border-navy-900/25 hover:shadow-sm'
      }`}
    >
      <span className="flex items-start justify-between gap-4">
        <span
          className={`flex size-12 items-center justify-center rounded-xl transition-colors ${
            selected ? 'bg-teal-700 text-white' : 'bg-navy-900 text-teal-300'
          }`}
        >
          <Icon name={trade.icon} className="size-6" />
        </span>
        <span
          className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-semibold ${
            selected ? 'bg-teal-50 text-teal-800' : 'text-navy-600 ring-1 ring-inset ring-navy-900/15'
          }`}
        >
          {selected ? (
            <>
              <Icon name="check" className="size-3.5" /> Selected
            </>
          ) : (
            'Select'
          )}
        </span>
      </span>

      <span className="mt-5 text-xl font-semibold text-navy-900">{trade.name}</span>
      <span className="mt-2 text-sm leading-relaxed text-navy-600">{trade.summary}</span>

      <span className="mt-5 block border-t border-navy-900/10 pt-4">
        <span className="sr-only">Common problems:</span>
        <span className="grid gap-2">
          {trade.examples.map((example) => (
            <span key={example} className="flex items-center gap-2 text-sm text-navy-700">
              <Icon name="check" className="size-4 shrink-0 text-teal-700" />
              {example}
            </span>
          ))}
        </span>
      </span>
    </button>
  )
}
