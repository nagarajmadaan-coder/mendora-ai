import Icon from './Icon'
import { DANGER_SIGNS } from '../data/content'

/*
  The list of "never DIY" situations. Used on the homepage, the intake
  screen and the About & Safety screen, so the wording is always identical.
  - "full": icon + title + explanation
  - "compact": title only, as a short bullet list
*/
export default function DangerSignList({ variant = 'full' }: { variant?: 'full' | 'compact' }) {
  if (variant === 'compact') {
    return (
      <ul className="space-y-2">
        {DANGER_SIGNS.map((sign) => (
          <li key={sign.title} className="flex items-center gap-2 text-sm font-medium">
            <Icon name={sign.icon} className="size-4 shrink-0" />
            {sign.title}
          </li>
        ))}
      </ul>
    )
  }

  return (
    <ul className="grid gap-4 sm:grid-cols-2">
      {DANGER_SIGNS.map((sign) => (
        <li key={sign.title} className="flex items-start gap-3">
          <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-red-50 text-red-700 ring-1 ring-inset ring-red-700/15">
            <Icon name={sign.icon} className="size-5" />
          </span>
          <span>
            <span className="block font-semibold text-navy-900">{sign.title}</span>
            <span className="mt-0.5 block text-sm leading-relaxed text-navy-600">{sign.detail}</span>
          </span>
        </li>
      ))}
    </ul>
  )
}
