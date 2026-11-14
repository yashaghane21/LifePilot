/**
 * API contract for the web app.
 *
 * Field names are snake_case to mirror the FastAPI/Pydantic responses exactly; these
 * types will later be generated from the backend's OpenAPI schema instead of written by hand.
 */

/** Decimal amount as a string, e.g. "250.00". Never do arithmetic on it in the browser. */
export type Money = string
/** ISO-8601 timestamp with offset, e.g. "2026-11-14T13:05:00+05:30". */
export type IsoDateTime = string
/** ISO-8601 calendar date, e.g. "2026-11-14". */
export type IsoDate = string

/** GET /api/v1/users/me */
export interface User {
  id: string
  email: string
  full_name: string
  created_at: IsoDateTime
}

/** POST /api/v1/auth/login and /auth/refresh */
export interface TokenResponse {
  access_token: string
  token_type: 'bearer'
  expires_in: number
}

export interface RegisterRequest {
  email: string
  full_name: string
  password: string
}

/** The backend's single error shape: {"error": {...}} */
export interface ApiErrorBody {
  code: string
  message: string
  request_id: string | null
  details?: { loc: (string | number)[]; message: string; type: string }[]
}

export type Domain = 'finance' | 'personal' | 'study' | 'fitness'
export type EntrySource = 'chat' | 'manual' | 'import'

export interface CategoryAmount {
  category: string
  amount: Money
}

export interface Budget {
  category: string
  spent: Money
  limit: Money
}

export interface ActivityItem {
  id: string
  occurred_at: IsoDateTime
  title: string
  domain: Domain
  source: EntrySource
  /** Human-readable pointer to the stored record, e.g. "expense #1042". */
  record_ref: string
}

export interface Task {
  id: string
  title: string
  done: boolean
}

export interface DashboardSummary {
  date: IsoDate
  week: {
    spent: Money
    top_categories: CategoryAmount[]
    dsa_solved: number
    dsa_goal: number
    gym_sessions: number
    gym_goal: number
    last_gym: { occurred_on: IsoDate; title: string } | null
  }
  last_weight: { kg: string; recorded_on: IsoDate; change_30d_kg: string } | null
  recent_activity: ActivityItem[]
  tasks: Task[]
  budgets: Budget[]
}

export interface Transaction {
  id: string
  date: IsoDate
  description: string
  category: string
  source: EntrySource
  amount: Money
}

export interface Borrowing {
  id: string
  person: string
  direction: 'owed_to_me' | 'i_owe'
  total: Money
  entries: { amount: Money; on: IsoDate }[]
}

export interface FinanceMonth {
  /** "YYYY-MM" */
  month: string
  spent: Money
  transaction_count: number
  income: Money
  income_note: string
  /** income − spent, computed by the backend with exact decimals. */
  net: Money
  owed_to_me: Money
  by_category: CategoryAmount[]
  budgets: Budget[]
  borrowings: Borrowing[]
  week: { start: IsoDate; end: IsoDate; total: Money; transactions: Transaction[] }
}

/** GET /api/v1/conversations (newest activity first) */
export interface ConversationSummary {
  id: string
  title: string
  created_at: IsoDateTime
  updated_at: IsoDateTime
}

/** A stored chat message. The metadata fields are set on assistant messages only. */
export interface StoredMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  created_at: IsoDateTime
  model: string | null
  input_tokens: number | null
  output_tokens: number | null
  /** USD as a decimal string, e.g. "0.00010800". */
  cost_usd: Money | null
  latency_ms: number | null
  /** 'stop' | 'length' | ... ('length' means the reply was cut off). */
  finish_reason: string | null
}

/** GET /api/v1/conversations/{id} */
export interface ConversationDetail extends ConversationSummary {
  messages: StoredMessage[]
}

/** POST /api/v1/chat. Omit conversation_id to start a new conversation. */
export interface ChatRequest {
  message: string
  conversation_id?: string
}

export interface ChatResponse {
  conversation: ConversationSummary
  user_message: StoredMessage
  assistant_message: StoredMessage
}
