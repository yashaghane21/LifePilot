// The only module pages use to get data. Today it serves mock data; each backend phase
// swaps one function for a real `fetch` to FastAPI without touching the pages.
import { mockDashboard, mockFinanceMonth } from './mock'
import type { DashboardSummary, FinanceMonth } from './types'

// Simulated network delay so loading states are built and visible from day one.
const MOCK_LATENCY_MS = 300

function respond<T>(data: T): Promise<T> {
  // structuredClone: callers get their own copy, as they would from a real response.
  return new Promise((resolve) => setTimeout(() => resolve(structuredClone(data)), MOCK_LATENCY_MS))
}

export const api = {
  getDashboard: (): Promise<DashboardSummary> => respond(mockDashboard),
  getFinanceMonth: (): Promise<FinanceMonth> => respond(mockFinanceMonth),
}
