// Sample data matching the approved UI mockup. Replaced by real API calls phase by phase.
import type { DashboardSummary, FinanceMonth } from './types'

export const mockDashboard: DashboardSummary = {
  date: '2026-11-14',
  week: {
    spent: '3480.00',
    top_categories: [
      { category: 'Food', amount: '1850.00' },
      { category: 'Transport', amount: '920.00' },
    ],
    dsa_solved: 9,
    dsa_goal: 14,
    gym_sessions: 3,
    gym_goal: 4,
    last_gym: { occurred_on: '2026-11-13', title: 'Push day' },
  },
  last_weight: { kg: '72.4', recorded_on: '2026-11-11', change_30d_kg: '-0.6' },
  recent_activity: [
    { id: 'a1', occurred_at: '2026-11-14T13:05:00+05:30', title: 'Spent ₹250 on food at Cafe Madras', domain: 'finance', source: 'chat', record_ref: 'expense #1042' },
    { id: 'a2', occurred_at: '2026-11-14T11:20:00+05:30', title: 'Got a haircut', domain: 'personal', source: 'chat', record_ref: 'activity #318' },
    { id: 'a3', occurred_at: '2026-11-14T09:40:00+05:30', title: 'Solved 2 DSA problems · Sliding window', domain: 'study', source: 'chat', record_ref: 'study log #77' },
    { id: 'a4', occurred_at: '2026-11-13T19:10:00+05:30', title: 'Gym · Push day, 55 min', domain: 'fitness', source: 'chat', record_ref: 'workout #64' },
    { id: 'a5', occurred_at: '2026-11-13T16:30:00+05:30', title: 'Lent ₹500 to Rutu', domain: 'finance', source: 'manual', record_ref: 'borrowing #12' },
  ],
  tasks: [
    { id: 't1', title: 'Solve 2 DSA problems', done: true },
    { id: 't2', title: 'Revise LLD: Parking lot design', done: false },
    { id: 't3', title: 'Leg day at the gym', done: false },
    { id: 't4', title: 'Pay electricity bill', done: false },
  ],
  budgets: [
    { category: 'Food', spent: '4860.00', limit: '6000.00' },
    { category: 'Shopping', spent: '3990.00', limit: '3500.00' },
    { category: 'Transport', spent: '2140.00', limit: '3000.00' },
  ],
}

export const mockFinanceMonth: FinanceMonth = {
  month: '2026-11',
  spent: '14230.00',
  transaction_count: 71,
  income: '40000.00',
  income_note: 'Stipend · 1 Nov',
  net: '25770.00',
  owed_to_me: '1200.00',
  by_category: [
    { category: 'Food', amount: '4860.00' },
    { category: 'Shopping', amount: '3990.00' },
    { category: 'Bills', amount: '2600.00' },
    { category: 'Transport', amount: '2140.00' },
    { category: 'Other', amount: '640.00' },
  ],
  budgets: mockDashboard.budgets,
  borrowings: [
    { id: 'b1', person: 'Rutu', direction: 'owed_to_me', total: '1200.00', entries: [{ amount: '700.00', on: '2026-11-03' }, { amount: '500.00', on: '2026-11-13' }] },
    { id: 'b2', person: 'Aman', direction: 'i_owe', total: '300.00', entries: [{ amount: '300.00', on: '2026-11-06' }] },
  ],
  week: {
    start: '2026-11-09',
    end: '2026-11-14',
    total: '3480.00',
    transactions: [
      { id: 'x1', date: '2026-11-14', description: 'Cafe Madras', category: 'Food', source: 'chat', amount: '250.00' },
      { id: 'x2', date: '2026-11-13', description: 'Metro card recharge', category: 'Transport', source: 'chat', amount: '500.00' },
      { id: 'x3', date: '2026-11-12', description: 'Groceries, DMart', category: 'Food', source: 'chat', amount: '1120.00' },
      { id: 'x4', date: '2026-11-11', description: 'Auto to college', category: 'Transport', source: 'chat', amount: '420.00' },
      { id: 'x5', date: '2026-11-10', description: 'Lunch with Rutu', category: 'Food', source: 'chat', amount: '480.00' },
      { id: 'x6', date: '2026-11-09', description: 'Notebooks and pens', category: 'Shopping', source: 'manual', amount: '710.00' },
    ],
  },
}
