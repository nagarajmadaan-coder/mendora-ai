import type { TradeId } from '../types'

/*
  Client for the MENDORA FastAPI backend.

  - The backend address comes from VITE_API_BASE_URL (see .env.example); default http://localhost:8000.
  - When signed in, the login token is attached automatically (see AuthContext).
  - Every failure becomes an ApiError with a status, a code and a readable message.
  - No API keys ever live here: the AI provider key stays on the backend.
*/

const DEFAULT_API_BASE_URL = 'http://localhost:8000'

// Unset → http://localhost:8000 (local development).
// Set to an empty value (VITE_API_BASE_URL=) → same website as the frontend, e.g. behind the Docker nginx proxy at /api.
export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? DEFAULT_API_BASE_URL).replace(/\/+$/, '')

/* ---------- Response shapes (they mirror backend/app/schemas.py) ---------- */

export type Role = 'customer' | 'technician' | 'admin'

export interface ApiTrade {
  id: TradeId
  name: string
}

export interface User {
  id: string
  email: string
  full_name: string
  role: Role
  is_active: boolean
  created_at: string
}

export interface TokenResponse {
  access_token: string
  token_type: 'bearer'
  expires_in: number
  user: User
}

export interface PossibleCause {
  title: string
  explanation: string
}

/* ---------- Safety assessment (rule-based, made by the backend before any AI) ---------- */

export type RiskLevel = 'low' | 'medium' | 'high'
export type SafetyAnswer = 'yes' | 'no' | 'not_sure'

export interface MatchedHazard {
  id: string
  category: 'electrical' | 'gas' | 'structural' | 'plumbing' | 'carpentry' | 'general'
  label: string
  risk: 'medium' | 'high'
  matched_text: string | null
}

export interface SafetyQuestion {
  id: string
  text: string
  options: SafetyAnswer[]
}

export interface SafetyAssessment {
  risk_level: RiskLevel
  matched_hazards: MatchedHazard[]
  /** True only for low risk. When false, no DIY guidance may be shown. */
  allow_diy: boolean
  requires_professional: boolean
  recommended_action: string
  safety_message: string
  /** True when the advice is to leave / move away from the area now. */
  emergency: boolean
  emergency_steps: string[]
  clarifying_questions: SafetyQuestion[]
  answered_questions: { id: string; text: string; answer: SafetyAnswer }[]
  resolved_hazards: string[]
  ai_diagnosis: 'full' | 'professional_only' | 'blocked'
  professional: string
  rules_version: string
  assessed_at: string
  disclaimer: string
}

export interface ClarifyingAnswer {
  question_id: string
  answer: SafetyAnswer
}

export interface Diagnosis {
  /** Only ever "ai". High-risk requests never get a diagnosis. */
  source: 'ai'
  summary: string
  possible_causes: PossibleCause[]
  follow_up_questions: string[]
  recommended_next_step: string
  professional_recommended: boolean
  professional_reason: string | null
  /** "professional_only" = medium risk: no DIY steps, the next step is always a professional. */
  safety_mode: 'full' | 'professional_only'
  /** True when MENDORA removed something the AI wrote because it wasn't safe to do yourself. */
  safety_filter_applied: boolean
  disclaimer: string
  /** True = made by the Tavily TRIAL mode (a web-search summary, not a full AI diagnosis). Older saved results lack it. */
  trial?: boolean
  sources?: { title: string; url: string; domain: string }[]
  provider: string | null
  model: string | null
  generated_at: string
}

export interface RepairRequest {
  request_id: string
  status: 'accepted' | 'diagnosed'
  trade: ApiTrade
  description: string
  created_at: string
  updated_at: string
  owned_by_account: boolean
  /** Always present. It decides what may happen next. */
  safety: SafetyAssessment
  diagnosis_status: 'not_started' | 'completed' | 'failed' | 'blocked_by_safety'
  /** Always null when the safety risk is high. */
  diagnosis: Diagnosis | null
  diagnosed_at: string | null
  last_diagnosis_error: string | null
  message: string
  safety_notice: string
}

export interface FollowUpAnswer {
  question: string
  answer: string
}

/* ---------- Knowledge base (Step 7) ---------- */

export interface KnowledgeCause {
  title: string
  explanation: string
  /** Always true: these are possibilities, never a confirmed diagnosis. */
  is_possibility: true
}

export interface KnowledgeEntry {
  id: string
  trade: TradeId
  category: string
  title: string
  symptoms: string[]
  professional_recommended: boolean
  professional_reason: string | null
  source: { type: string; verification_status: 'unverified' | 'professionally_reviewed'; note: string }
  clarifying_questions: string[]
  possible_causes: KnowledgeCause[]
  safety_restrictions: string[]
  hazard_categories: string[]
  /** Empty unless the safety check allows guidance. */
  next_steps: string[]
  steps_shown: boolean
  steps_note: string | null
}

export interface SimilarCase {
  case_id: string
  trade: TradeId
  category: string | null
  symptoms_summary: string
  confirmed_cause: string
  parts_used: string[]
  completion_minutes: number | null
  cost_amount: number | null
  currency: string | null
  relevance: number
}

export interface KnowledgeGuidance {
  status: 'matched' | 'no_match' | 'blocked_by_safety'
  mode: 'full' | 'professional_only' | 'blocked'
  message: string
  safety: SafetyAssessment
  matches: { entry: KnowledgeEntry; relevance: number; matched_terms: string[] }[]
  similar_verified_cases: SimilarCase[]
  retriever: string
  knowledge_version: string
  disclaimer: string
}

/* ---------- AI web research (Tavily) — a summary of web pages, NOT a diagnosis ---------- */

export interface WebResearch {
  provider: 'tavily'
  /** full = low risk; sources_only = medium risk (links only). */
  mode: 'full' | 'sources_only'
  query_sent: string
  answer: string | null
  answer_note: string | null
  sources: { title: string; url: string; domain: string; snippet: string | null }[]
  safety_filter_applied: boolean
  disclaimer: string
  generated_at: string
}

/* ---------- Technicians (Step 8) ---------- */

export type Availability = 'available' | 'busy' | 'unavailable'
export type VerificationStatus = 'unverified' | 'pending' | 'verified' | 'rejected'

export interface Technician {
  id: string
  display_name: string
  trade: TradeId
  service_areas: string[]
  skills: string[]
  years_experience: number | null
  bio: string | null
  verification_status: VerificationStatus
  verification_label: string
  is_sample: boolean
  sample_notice: string | null
  availability_status: Availability
  visit_rate: number | null
  consultation_rate: number | null
  offers_consultation: boolean
  currency: string
  reviews: { average: number | null; count: number; note: string }
  contact_method: 'in_app_booking'
}

export interface TechnicianProfile extends Technician {
  user_id: string
  verification_note: string | null
  verified_at: string | null
  created_at: string
  updated_at: string
}

export interface TechnicianProfileInput {
  display_name: string
  trade: TradeId
  service_areas: string[]
  skills: string[]
  years_experience: number | null
  bio: string | null
  visit_rate: number | null
  consultation_rate: number | null
}

/** An APPROXIMATE area-centre point (never an exact address). */
export interface MapPoint {
  lat: number
  lon: number
  label: string
  approximate: true
}

export interface TechnicianMatch {
  technician: Technician
  match_score: number
  match_reasons: string[]
  /** Rough distance between area centres (not addresses), to 0.5 km. */
  approx_distance_km: number | null
  map_point: MapPoint | null
}

export interface TechnicianSearchResult {
  results: TechnicianMatch[]
  total: number
  sort_note: string
  demo_mode: boolean
  message: string | null
  search_point: MapPoint | null
  /** When nothing matched the area: the areas that ARE covered (for the chosen trade). */
  covered_areas: string[]
}

/* ---------- Bookings & consultations (Step 9) ---------- */

export type BookingType = 'technician_visit' | 'expert_consultation'
export type BookingStatus = 'requested' | 'accepted' | 'rejected' | 'cancelled' | 'completed'
export type BookingAction = 'accept' | 'reject' | 'cancel' | 'complete'

export interface TechnicianSummary {
  id: string
  display_name: string
  trade: string
  is_sample: boolean
  sample_notice: string | null
  verification_label: string
}

export interface Booking {
  id: string
  booking_type: BookingType
  status: BookingStatus
  status_reason: string | null
  scheduled_start: string
  scheduled_end: string
  duration_minutes: number
  local_time_label: string
  timezone: string
  technician: TechnicianSummary
  repair_request: { id: string; trade: string; description: string; risk_level: string }
  customer_display_name: string
  service_area: string | null
  /** Hidden from the technician until they accept. */
  service_address: string | null
  address_note: string | null
  customer_note: string | null
  price_amount: number | null
  price_currency: string
  price_note: string
  safety_risk_level: string
  safety_acknowledged: boolean
  history: { status: BookingStatus; at: string; by: string; reason: string | null }[]
  /** What the signed-in user may do next. */
  allowed_actions: BookingAction[]
  consultation_note: string | null
  /** Sandbox payment summary for this booking. */
  payment: BookingPayment
  /** Visit fee + technician's estimate, with the (sandbox) platform fee split. */
  price_breakdown: PriceBreakdown
  /** 'propose' (technician) or 'approve' / 'decline' (customer). */
  estimate_actions: ('propose' | 'approve' | 'decline')[]
  review: Review | null
  can_review: boolean
  created_at: string
  updated_at: string
}

/* ---------- Sandbox payments (Step 10) — simulated, no real money ---------- */

export type PaymentStatus = 'pending' | 'succeeded' | 'failed' | 'refunded'
export type BookingPaymentStatus = 'not_payable' | 'unpaid' | 'paid' | 'refunded'
export type SandboxScenario = 'success' | 'card_declined' | 'insufficient_funds' | 'processing_error'

export interface Payment {
  id: string
  booking_id: string
  amount: number
  currency: string
  status: PaymentStatus
  method_type: string
  provider: string
  sandbox: boolean
  /** Simulated reference — not a real bank transaction. */
  transaction_ref: string | null
  failure_code: string | null
  failure_message: string | null
  refund_ref: string | null
  refunded_at: string | null
  created_at: string
  updated_at: string
}

export interface PriceBreakdown {
  status: 'listed_rate' | 'proposed' | 'approved' | 'declined'
  currency: string
  visit_fee: number | null
  labour: number
  materials: number
  total: number | null
  commission_percent: number
  platform_fee: number
  technician_earnings: number
  estimate_note: string | null
  note: string
}

export interface Review {
  id: string
  rating: number
  comment: string | null
  booking_type: string
  author: string
  verified_booking: true
  created_at: string
}

export interface RequestPhoto {
  id: string
  content_type: string
  size_bytes: number
  created_at: string
  url: string
}

export interface AdminTechnician extends Technician {
  user_id: string
  verification_note: string | null
  verified_at: string | null
  created_at: string
  updated_at: string
}

export interface RepairCase {
  id: string
  trade: TradeId
  category: string | null
  symptoms: string
  confirmed_cause: string | null
  cause_source: 'technician_confirmed' | 'customer_reported' | 'ai_suggestion'
  parts_used: string[]
  completion_minutes: number | null
  cost_amount: number | null
  currency: string | null
  verification_status: 'unverified' | 'verified' | 'rejected'
  verification_basis: string | null
  rejection_reason: string | null
  booking_id: string | null
  created_at: string
}

export interface AdminStats {
  users: Record<string, number>
  repair_requests: { total: number; by_risk: Record<string, number> }
  bookings: Record<string, number>
  payments_sandbox: { by_status: Record<string, number>; succeeded_totals: { currency: string; count: number; amount: number }[]; note: string }
  technicians: { by_verification: Record<string, number>; samples: number }
  repair_cases: Record<string, number>
  reviews: { count: number; average: number | null }
  system: {
    ai_diagnosis: { provider: string; model: string | null; configured: boolean }
    web_research: { provider: string; configured: boolean }
    payments_provider: string
    demo_mode: boolean
  }
}

export interface SafetyEscalation {
  request_id: string
  trade: string
  created_at: string | null
  hazards: string[]
  description: string
  has_account: boolean
  bookings: number
}

export interface BookingPayment {
  status: BookingPaymentStatus
  /** True when the signed-in user can pay now. */
  can_pay: boolean
  amount: number | null
  currency: string
  reason: string | null
  /** Most recent attempt (customer and admin only). */
  latest: Payment | null
  /** Sandbox escrow: held until the job is completed, then released (simulated). */
  payout_status: 'held' | 'released' | 'returned' | null
  payout_note: string | null
  sandbox_notice: string
}

export interface PaymentResult {
  payment: Payment
  booking_payment_status: BookingPaymentStatus
  replayed: boolean
  message: string
  sandbox_notice: string
}

export interface BookingInput {
  technician_id: string
  repair_request_id: string
  booking_type: BookingType
  scheduled_start?: string
  next_available?: boolean
  service_area?: string
  service_address?: string
  customer_note?: string
  safety_acknowledged?: boolean
}

export interface BookingQuote {
  technician: TechnicianSummary
  booking_type: BookingType
  scheduled_start: string
  scheduled_end: string
  local_time_label: string
  duration_minutes: number
  price_amount: number | null
  price_currency: string
  price_note: string
  safety_risk_level: string
  requires_safety_acknowledgement: boolean
  safety_message: string | null
  emergency_steps: string[]
  notes: string[]
}

export interface TimeSlot {
  start: string
  end: string
  local_time: string
}

export interface AvailabilityResult {
  technician_id: string
  date: string
  timezone: string
  booking_type: BookingType
  duration_minutes: number
  slots: TimeSlot[]
  message: string | null
}

export interface AppNotification {
  id: string
  booking_id: string | null
  kind: string
  message: string
  created_at: string
  read: boolean
}

export interface NotificationList {
  notifications: AppNotification[]
  unread_count: number
  channel: 'in_app'
  note: string
}

export interface ApiErrorDetail {
  field: string | null
  message: string
}

/** Thrown for any failed call. `status` is 0 when the server couldn't be reached at all. */
export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly details: ApiErrorDetail[]

  constructor(status: number, code: string, message: string, details: ApiErrorDetail[] = []) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.details = details
  }

  /** Message for one form field, if the server reported a problem with it. */
  fieldMessage(field: string): string | undefined {
    return this.details.find((d) => d.field === field)?.message
  }
}

/* ---------- Auth token wiring (set by AuthContext) ---------- */

let currentToken: string | null = null
let onUnauthorized: (() => void) | null = null

export function setAuthToken(token: string | null) {
  currentToken = token
}

export function setUnauthorizedHandler(handler: (() => void) | null) {
  onUnauthorized = handler
}

/* ---------- Low-level request helper ---------- */

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const sentToken = currentToken
  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: {
        Accept: 'application/json',
        ...(init.body ? { 'Content-Type': 'application/json' } : {}),
        ...(sentToken ? { Authorization: `Bearer ${sentToken}` } : {}),
        ...init.headers,
      },
    })
  } catch {
    throw new ApiError(
      0,
      'network_error',
      'Could not reach the MENDORA server. Please check that the backend is running and try again.',
    )
  }

  const data = await response.json().catch(() => null)
  if (!response.ok) {
    const error = data?.error
    // An expired or invalid token: sign the user out everywhere.
    if (response.status === 401 && sentToken && onUnauthorized) onUnauthorized()
    throw new ApiError(
      response.status,
      error?.code ?? 'http_error',
      error?.message ?? `Request failed with status ${response.status}.`,
      error?.details ?? [],
    )
  }
  return data as T
}

/* ---------- Endpoints ---------- */

export const api = {
  health: () => request<{ status: 'ok'; ai_diagnosis: { configured: boolean } }>('/api/health'),

  listTrades: async () => (await request<{ trades: ApiTrade[] }>('/api/trades')).trades,

  // ----- Auth -----
  register: (input: { email: string; password: string; full_name: string }) =>
    request<TokenResponse>('/api/auth/register', { method: 'POST', body: JSON.stringify(input) }),

  login: (input: { email: string; password: string }) =>
    request<TokenResponse>('/api/auth/login', { method: 'POST', body: JSON.stringify(input) }),

  me: () => request<User>('/api/auth/me'),

  // ----- Safety (works without signing in; nothing is saved) -----
  assessSafety: (input: { trade_id: TradeId; description: string; clarifying_answers?: ClarifyingAnswer[] }) =>
    request<SafetyAssessment>('/api/safety/assess', { method: 'POST', body: JSON.stringify(input) }),

  // ----- Repair requests -----
  createRepairRequest: (input: { trade_id: TradeId; description: string; clarifying_answers?: ClarifyingAnswer[] }) =>
    request<RepairRequest>('/api/repair-requests', { method: 'POST', body: JSON.stringify(input) }),

  answerSafetyQuestions: (requestId: string, answers: ClarifyingAnswer[]) =>
    request<RepairRequest>(`/api/repair-requests/${encodeURIComponent(requestId)}/safety-answers`, {
      method: 'POST',
      body: JSON.stringify({ answers }),
    }),

  getRepairRequest: (requestId: string) =>
    request<RepairRequest>(`/api/repair-requests/${encodeURIComponent(requestId)}`),

  listMyRepairRequests: (limit = 50) =>
    request<{ items: RepairRequest[]; total: number }>(`/api/repair-requests?limit=${limit}`),

  /**
   * Runs the AI diagnosis on the server. The server re-checks safety first:
   * high risk → ApiError 409 "blocked_by_safety". Can take a while; may fail with ai_* error codes.
   */
  diagnose: (requestId: string, followUpAnswers: FollowUpAnswer[] = []) =>
    request<RepairRequest>(`/api/repair-requests/${encodeURIComponent(requestId)}/diagnosis`, {
      method: 'POST',
      body: JSON.stringify({ follow_up_answers: followUpAnswers }),
    }),

  // ----- AI web research via Tavily (server re-checks safety; high risk → 409) -----
  webResearch: (requestId: string) =>
    request<WebResearch>(`/api/repair-requests/${encodeURIComponent(requestId)}/web-research`, { method: 'POST' }),

  // ----- Knowledge base (safety is checked on the server first) -----
  getGuidance: (requestId: string) =>
    request<KnowledgeGuidance>(`/api/repair-requests/${encodeURIComponent(requestId)}/guidance`),

  // ----- Technicians -----
  searchTechnicians: (params: { trade?: TradeId | ''; area?: string; available?: boolean; consultation?: boolean }) => {
    const q = new URLSearchParams()
    if (params.trade) q.set('trade', params.trade)
    if (params.area?.trim()) q.set('area', params.area.trim())
    if (params.available) q.set('available', 'true')
    if (params.consultation) q.set('consultation', 'true')
    const query = q.toString()
    return request<TechnicianSearchResult>(`/api/technicians${query ? `?${query}` : ''}`)
  },

  getTechnician: (id: string) => request<Technician>(`/api/technicians/${encodeURIComponent(id)}`),

  getAvailability: (id: string, date: string, bookingType: BookingType) =>
    request<AvailabilityResult>(
      `/api/technicians/${encodeURIComponent(id)}/availability?date=${encodeURIComponent(date)}&booking_type=${bookingType}`,
    ),

  // ----- My technician profile (technician accounts) -----
  getMyTechnicianProfile: () => request<TechnicianProfile>('/api/technician/profile'),

  saveMyTechnicianProfile: (input: TechnicianProfileInput) =>
    request<TechnicianProfile>('/api/technician/profile', { method: 'PUT', body: JSON.stringify(input) }),

  submitForVerification: () =>
    request<TechnicianProfile>('/api/technician/profile/submit-verification', { method: 'POST' }),

  setAvailability: (availability_status: Availability) =>
    request<TechnicianProfile>('/api/technician/availability', {
      method: 'PATCH',
      body: JSON.stringify({ availability_status }),
    }),

  // ----- Bookings -----
  quoteBooking: (input: BookingInput) =>
    request<BookingQuote>('/api/bookings/quote', { method: 'POST', body: JSON.stringify(input) }),

  createBooking: (input: BookingInput) =>
    request<Booking>('/api/bookings', { method: 'POST', body: JSON.stringify(input) }),

  listBookings: (status?: BookingStatus) =>
    request<{ bookings: Booking[]; total: number }>(`/api/bookings${status ? `?status=${status}` : ''}`),

  getBooking: (id: string) => request<Booking>(`/api/bookings/${encodeURIComponent(id)}`),

  bookingAction: (id: string, action: BookingAction, body?: object) =>
    request<Booking>(`/api/bookings/${encodeURIComponent(id)}/${action}`, {
      method: 'POST',
      ...(body ? { body: JSON.stringify(body) } : {}),
    }),

  // ----- Sandbox payments (no real money; no card details are ever sent) -----
  payBooking: (bookingId: string, input: { expected_amount: number; currency: string; scenario: SandboxScenario; idempotency_key: string }) =>
    request<PaymentResult>(`/api/bookings/${encodeURIComponent(bookingId)}/payments`, { method: 'POST', body: JSON.stringify(input) }),

  listBookingPayments: (bookingId: string) =>
    request<{ payments: Payment[]; total: number; sandbox_notice: string }>(`/api/bookings/${encodeURIComponent(bookingId)}/payments`),

  // ----- Estimates & reviews -----
  proposeEstimate: (bookingId: string, input: { labour: number; materials: number; note?: string }) =>
    request<Booking>(`/api/bookings/${encodeURIComponent(bookingId)}/estimate`, { method: 'POST', body: JSON.stringify(input) }),

  decideEstimate: (bookingId: string, approve: boolean, reason?: string) =>
    request<Booking>(`/api/bookings/${encodeURIComponent(bookingId)}/estimate/${approve ? 'approve' : 'decline'}`, {
      method: 'POST',
      ...(approve ? {} : { body: JSON.stringify({ reason: reason || null }) }),
    }),

  reviewBooking: (bookingId: string, input: { rating: number; comment?: string }) =>
    request<Review>(`/api/bookings/${encodeURIComponent(bookingId)}/review`, { method: 'POST', body: JSON.stringify(input) }),

  technicianReviews: (technicianId: string) =>
    request<{ reviews: Review[]; average: number | null; count: number; note: string }>(`/api/technicians/${encodeURIComponent(technicianId)}/reviews`),

  // ----- Photos (owner, admins, and the technician after acceptance) -----
  listPhotos: (requestId: string) =>
    request<{ photos: RequestPhoto[]; max_photos: number; note: string }>(`/api/repair-requests/${encodeURIComponent(requestId)}/photos`),

  uploadPhoto: (requestId: string, dataBase64: string) =>
    request<RequestPhoto>(`/api/repair-requests/${encodeURIComponent(requestId)}/photos`, {
      method: 'POST',
      body: JSON.stringify({ data_base64: dataBase64 }),
    }),

  deletePhoto: (photoUrl: string) => request<null>(photoUrl, { method: 'DELETE' }),

  /** Photos need the sign-in token, so they're fetched as a blob and shown with a local object URL. */
  photoBlob: async (photoUrl: string): Promise<Blob> => {
    const response = await fetch(`${API_BASE_URL}${photoUrl}`, { headers: currentToken ? { Authorization: `Bearer ${currentToken}` } : {} })
    if (!response.ok) throw new ApiError(response.status, 'photo_error', 'The photo couldn’t be loaded.')
    return response.blob()
  },

  // ----- Knowledge base (browse; no repair steps here) -----
  listKnowledge: (trade?: TradeId) =>
    request<{ entries: (Omit<KnowledgeEntry, 'next_steps' | 'steps_shown' | 'steps_note' | 'clarifying_questions' | 'possible_causes' | 'safety_restrictions' | 'hazard_categories' | 'professional_reason'>)[]; total: number; knowledge_version: string; note: string }>(
      `/api/knowledge/entries${trade ? `?trade=${trade}` : ''}`,
    ),

  getKnowledgeEntry: (id: string) =>
    request<Omit<KnowledgeEntry, 'next_steps' | 'steps_shown' | 'steps_note'>>(`/api/knowledge/entries/${encodeURIComponent(id)}`),

  // ----- Admin -----
  adminStats: () => request<AdminStats>('/api/admin/stats'),
  adminEscalations: () => request<{ items: SafetyEscalation[]; total: number; note: string }>('/api/admin/safety-escalations'),
  adminTechnicians: (status?: string) =>
    request<{ technicians: AdminTechnician[]; total: number }>(`/api/admin/technicians${status ? `?status=${status}` : ''}`),
  adminVerifyTechnician: (id: string, decision: 'verified' | 'rejected', note: string) =>
    request<AdminTechnician>(`/api/admin/technicians/${encodeURIComponent(id)}/verification`, { method: 'POST', body: JSON.stringify({ decision, note }) }),
  adminCases: (status?: string) => request<{ cases: RepairCase[]; total: number }>(`/api/admin/cases${status ? `?status=${status}` : ''}`),
  adminVerifyCase: (id: string, basis: string) =>
    request<RepairCase>(`/api/admin/cases/${encodeURIComponent(id)}/verify`, { method: 'POST', body: JSON.stringify({ basis }) }),
  adminRejectCase: (id: string, reason: string) =>
    request<RepairCase>(`/api/admin/cases/${encodeURIComponent(id)}/reject`, { method: 'POST', body: JSON.stringify({ reason }) }),

  // ----- In-app notifications -----
  listNotifications: () => request<NotificationList>('/api/notifications'),

  markNotificationRead: (id: string) =>
    request<AppNotification>(`/api/notifications/${encodeURIComponent(id)}/read`, { method: 'POST' }),

  markAllNotificationsRead: () => request<NotificationList>('/api/notifications/read-all', { method: 'POST' }),
}
