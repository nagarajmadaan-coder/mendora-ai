import type { DangerSign, NavItem, ProcessStep, Resolution, Trade, TradeId } from '../types'

/*
  All the app's wording lives here, separate from the layout code.
  To change text, edit this file — the components update automatically.
*/

/** Every screen's URL in one place, so links never get out of sync. */
export const ROUTES = {
  home: '/',
  diagnose: '/diagnose',
  resolutions: '/resolutions',
  about: '/about',
  login: '/login',
  register: '/register',
  account: '/account',
  requestPrefix: '/requests/',
  technicians: '/technicians',
  book: '/book',
  bookings: '/bookings',
  bookingPrefix: '/bookings/',
  technicianProfile: '/technician/profile',
  admin: '/admin',
  guides: '/guides',
} as const

export function bookingUrl(bookingId: string): string {
  return `${ROUTES.bookingPrefix}${encodeURIComponent(bookingId)}`
}

/** Link to the technician finder, optionally pre-filtered. */
export function techniciansUrl(params: { trade?: TradeId; consultation?: boolean; request?: string } = {}): string {
  const q = new URLSearchParams()
  if (params.trade) q.set('trade', params.trade)
  if (params.consultation) q.set('consultation', '1')
  if (params.request) q.set('request', params.request)
  const query = q.toString()
  return query ? `${ROUTES.technicians}?${query}` : ROUTES.technicians
}

/** Link to the booking screen for one technician. */
export function bookUrl(technicianId: string, type: 'technician_visit' | 'expert_consultation', requestId?: string): string {
  const q = new URLSearchParams({ technician: technicianId, type })
  if (requestId) q.set('request', requestId)
  return `${ROUTES.book}?${q.toString()}`
}

export function diagnoseUrl(trade?: TradeId): string {
  return trade ? `${ROUTES.diagnose}?trade=${trade}` : ROUTES.diagnose
}

export function requestUrl(requestId: string): string {
  return `${ROUTES.requestPrefix}${encodeURIComponent(requestId)}`
}

/** Sign-in link that brings the user back to `next` afterwards. */
export function loginUrl(next?: string, reason?: 'diagnose' | 'account' | 'book'): string {
  const params = new URLSearchParams()
  if (next) params.set('next', next)
  if (reason) params.set('reason', reason)
  const query = params.toString()
  return query ? `${ROUTES.login}?${query}` : ROUTES.login
}

/** Only allow returning to pages inside this app (never to another website). */
export function safeNextPath(next: string | null): string {
  return next && next.startsWith('/') && !next.startsWith('//') && !next.includes('\\') ? next : ROUTES.account
}

export const NAV_ITEMS: NavItem[] = [
  { label: 'Services', to: '/#services' },
  { label: 'How it works', to: '/#how-it-works' },
  { label: 'Resolutions', to: ROUTES.resolutions },
  { label: 'Technicians', to: ROUTES.technicians },
  { label: 'Guides', to: ROUTES.guides },
  { label: 'About & Safety', to: ROUTES.about },
]

export const TRADES: Trade[] = [
  {
    id: 'plumbing',
    name: 'Plumbing',
    summary: 'Leaks, blockages and water problems around the kitchen, bathroom and pipes.',
    examples: ['Leaking taps and pipes', 'Blocked drains and toilets', 'Low water pressure', 'Water heater issues'],
    icon: 'droplet',
  },
  {
    id: 'electrical',
    name: 'Electrical',
    summary: 'Faults with switches, sockets, lighting and the circuits behind them.',
    examples: ['Tripping breakers', 'Dead sockets or switches', 'Flickering lights', 'Fan and fixture faults'],
    icon: 'bolt',
  },
  {
    id: 'carpentry',
    name: 'Carpentry',
    summary: 'Doors, cabinets, furniture and woodwork that are stuck, loose or damaged.',
    examples: ['Sticking doors and drawers', 'Loose hinges and handles', 'Damaged shelves or cabinets', 'Wobbly furniture'],
    icon: 'hammer',
  },
]

export function isTradeId(value: unknown): value is TradeId {
  return TRADES.some((trade) => trade.id === value)
}

export function getTrade(id: TradeId): Trade {
  return TRADES.find((trade) => trade.id === id)!
}

export const PROCESS_STEPS: ProcessStep[] = [
  {
    title: 'Describe the problem',
    description:
      'Choose the trade, describe what is happening in your own words and, if you like, add a photo.',
    icon: 'message',
  },
  {
    title: 'AI assesses the issue',
    description:
      'MENDORA’s AI will look at the likely causes, how serious the problem is, and whether it is safe for you to handle yourself.',
    icon: 'search',
  },
  {
    title: 'Choose a resolution',
    description:
      'Fix it yourself with guided steps, talk it through with an expert, or request a technician visit.',
    icon: 'split',
  },
]

export const RESOLUTIONS: Resolution[] = [
  {
    id: 'ai-fix',
    title: 'AI Fix',
    description:
      'Simple, safe checks for low-risk problems, from MENDORA’s repair guides. The AI diagnosis needs an AI provider, which isn’t connected yet.',
    bestFor: 'Minor jobs you can safely do yourself',
    includes: ['Safety check first, always', 'Matching repair guides (not yet professionally reviewed)', 'AI diagnosis once a provider is set up'],
    icon: 'sparkles',
    statusLabel: 'Guides available · AI not connected',
    cta: { label: 'Describe a problem', to: '/diagnose' },
  },
  {
    id: 'expert',
    title: 'Talk to an Expert',
    description:
      'Request a 30-minute consultation with a technician who offers expert advice. Choose a time or the next free slot.',
    bestFor: 'When you are unsure or stuck',
    includes: ['See the rate before you confirm', 'Track the request status', 'Live audio/video calls are not connected yet'],
    icon: 'phone',
    statusLabel: 'Sandbox payment',
    cta: { label: 'Find an expert', to: '/technicians?consultation=1' },
  },
  {
    id: 'technician',
    title: 'Send a Technician',
    description: 'Request a home visit from a technician whose service area covers yours.',
    bestFor: 'Bigger, riskier or specialist repairs',
    includes: ['Matched by trade and service area (not distance)', 'See the listed rate before you confirm', 'Sandbox payment demo — no real money'],
    icon: 'mapPin',
    statusLabel: 'Sandbox payment',
    cta: { label: 'Find a technician', to: '/technicians' },
  },
]

/** The "never DIY" situations, shown on the homepage, intake and About & Safety screens. */
export const DANGER_SIGNS: DangerSign[] = [
  {
    title: 'Sparking electrical equipment',
    detail: 'Sparks, buzzing, scorch marks, hot sockets or exposed and damaged wiring.',
    icon: 'bolt',
  },
  {
    title: 'Suspected gas leak',
    detail: 'A smell of gas (rotten eggs) or a hissing sound near a gas line, cylinder or appliance.',
    icon: 'flame',
  },
  {
    title: 'Smoke or burning',
    detail: 'Smoke, or a burning or melting-plastic smell from sockets, switches or appliances.',
    icon: 'wind',
  },
  {
    title: 'Structural danger',
    detail: 'Cracked beams, sagging ceilings, failing supports, or water pouring through a ceiling.',
    icon: 'building',
  },
]

export const EMERGENCY_STEPS: string[] = [
  'Move everyone — including pets — away from the danger.',
  'Only if it is safe to reach, switch off the mains power, gas supply or water stop valve.',
  'For a gas smell: do not use switches, flames or phones near the area. Open doors and windows on your way out.',
  'Call your local emergency number (for example 112 in India and the EU, or 911 in the US), your gas provider’s emergency line, or a qualified professional.',
]
