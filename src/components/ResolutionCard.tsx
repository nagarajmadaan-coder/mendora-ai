import Icon from './Icon'
import Badge from './Badge'
import Button from './Button'
import type { Resolution } from '../types'

interface ResolutionCardProps {
  resolution: Resolution
  /** Show the "What it will include" list (used on the Resolution Options screen) */
  detailed?: boolean
}

/*
  One resolution option. The badge says honestly how much of it works today
  (e.g. payments are a sandbox demo only, and there are no live calls).
*/
export default function ResolutionCard({ resolution, detailed = false }: ResolutionCardProps) {
  return (
    <article
      aria-labelledby={`resolution-${resolution.id}`}
      className="flex h-full flex-col rounded-2xl border border-navy-900/10 bg-white p-6"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <span className="flex size-12 items-center justify-center rounded-xl bg-teal-50 text-teal-700 ring-1 ring-inset ring-teal-700/15">
          <Icon name={resolution.icon} className="size-6" />
        </span>
        <Badge tone="amber" icon="clock">
          {resolution.statusLabel}
        </Badge>
      </div>

      <h3 id={`resolution-${resolution.id}`} className="mt-5 text-xl font-semibold text-navy-900">
        {resolution.title}
      </h3>
      <p className={`mt-2 leading-relaxed text-navy-600 ${detailed ? '' : 'flex-1'}`}>{resolution.description}</p>

      {detailed && (
        <div className="mt-5 flex-1">
          <h4 className="text-sm font-semibold text-navy-900">What it will include</h4>
          <ul className="mt-2 space-y-2">
            {resolution.includes.map((item) => (
              <li key={item} className="flex items-start gap-2 text-sm text-navy-700">
                <Icon name="check" className="mt-0.5 size-4 shrink-0 text-teal-700" />
                {item}
              </li>
            ))}
          </ul>
        </div>
      )}

      <p className="mt-5 border-t border-navy-900/10 pt-4 text-sm">
        <span className="font-semibold text-navy-900">Best for: </span>
        <span className="text-navy-700">{resolution.bestFor}</span>
      </p>
      {detailed && resolution.cta && (
        <Button to={resolution.cta.to} variant="secondary" className="mt-4">
          {resolution.cta.label}
        </Button>
      )}
    </article>
  )
}
