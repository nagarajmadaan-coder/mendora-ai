import type { IconName } from './components/Icon'

// Shared TypeScript types. Defining them once keeps data and components consistent.

export type TradeId = 'plumbing' | 'electrical' | 'carpentry'

export interface Trade {
  id: TradeId
  name: string
  summary: string
  examples: string[]
  icon: IconName
}

export interface ProcessStep {
  title: string
  description: string
  icon: IconName
}

export interface Resolution {
  id: 'ai-fix' | 'expert' | 'technician'
  title: string
  description: string
  bestFor: string
  /** What the option will include once it is built */
  includes: string[]
  icon: IconName
  /** Honest label for how much of this option works today */
  statusLabel: string
  /** Where the option starts, if it can be used yet */
  cta?: { label: string; to: string }
}

export interface DangerSign {
  title: string
  detail: string
  icon: IconName
}

export interface NavItem {
  label: string
  to: string
}
