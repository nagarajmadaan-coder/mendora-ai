import type { ReactNode } from 'react'
import Icon, { type IconName } from './Icon'

/* Small rounded label, e.g. "Booking requests only". One style per meaning. */

type Tone = 'teal' | 'amber' | 'navy' | 'red'

const TONES: Record<Tone, string> = {
  teal: 'bg-teal-50 text-teal-800 ring-teal-700/20',
  amber: 'bg-amber-50 text-amber-900 ring-amber-700/25',
  navy: 'bg-navy-50 text-navy-800 ring-navy-900/15',
  red: 'bg-red-50 text-red-800 ring-red-700/20',
}

interface BadgeProps {
  tone?: Tone
  icon?: IconName
  children: ReactNode
}

export default function Badge({ tone = 'navy', icon, children }: BadgeProps) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-semibold whitespace-nowrap ring-1 ring-inset ${TONES[tone]}`}
    >
      {icon && <Icon name={icon} className="size-3.5" />}
      {children}
    </span>
  )
}
