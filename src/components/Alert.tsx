import type { ReactNode } from 'react'
import Icon, { type IconName } from './Icon'

/* A coloured message box. One style per meaning, used everywhere for consistency. */

type Tone = 'info' | 'success' | 'warning' | 'error'

const STYLES: Record<Tone, { box: string; icon: IconName; iconColor: string }> = {
  info: { box: 'border-navy-900/15 bg-navy-50 text-navy-800', icon: 'info', iconColor: 'text-navy-700' },
  success: { box: 'border-teal-700/20 bg-teal-50 text-navy-800', icon: 'checkCircle', iconColor: 'text-teal-700' },
  warning: { box: 'border-amber-600/25 bg-amber-50 text-navy-800', icon: 'info', iconColor: 'text-amber-700' },
  error: { box: 'border-red-700/20 bg-red-50 text-red-900', icon: 'alert', iconColor: 'text-red-700' },
}

interface AlertProps {
  tone?: Tone
  title?: string
  children?: ReactNode
  /** role="alert" makes screen readers announce it immediately (use for errors that just appeared) */
  announce?: boolean
  action?: ReactNode
}

export default function Alert({ tone = 'info', title, children, announce = false, action }: AlertProps) {
  const style = STYLES[tone]
  return (
    <div role={announce ? 'alert' : undefined} className={`flex items-start gap-3 rounded-xl border p-4 ${style.box}`}>
      <Icon name={style.icon} className={`mt-0.5 size-5 shrink-0 ${style.iconColor}`} />
      <div className="min-w-0 flex-1">
        {title && <p className="font-semibold">{title}</p>}
        {children && <div className={`text-sm leading-relaxed ${title ? 'mt-1' : ''}`}>{children}</div>}
        {action && <div className="mt-3">{action}</div>}
      </div>
    </div>
  )
}
