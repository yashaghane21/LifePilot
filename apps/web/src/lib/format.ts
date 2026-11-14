import type { IsoDate, IsoDateTime, Money } from '../api/types'

const inr = new Intl.NumberFormat('en-IN', {
  style: 'currency',
  currency: 'INR',
  minimumFractionDigits: 0,
  maximumFractionDigits: 2,
})

/** "1850.00" → "₹1,850". Converting to a number is safe here: display only, no arithmetic. */
export function formatMoney(amount: Money): string {
  return inr.format(Number(amount))
}

/** Display-only ratio for progress bars, clamped to 0..1. */
export function ratio(part: Money, whole: Money): number {
  const w = Number(whole)
  return w > 0 ? Math.min(Math.max(Number(part) / w, 0), 1) : 0
}

// Calendar dates carry no time zone; parse as UTC and format as UTC so the day never shifts.
const dayMonth = new Intl.DateTimeFormat('en-IN', { day: 'numeric', month: 'short', timeZone: 'UTC' })
const weekdayLong = new Intl.DateTimeFormat('en-IN', {
  weekday: 'long',
  day: 'numeric',
  month: 'long',
  timeZone: 'UTC',
})
const monthYear = new Intl.DateTimeFormat('en-IN', { month: 'long', year: 'numeric', timeZone: 'UTC' })
const time24 = new Intl.DateTimeFormat('en-IN', { hour: '2-digit', minute: '2-digit', hourCycle: 'h23' })

/** "2026-11-14" → "14 Nov" */
export function formatDayMonth(date: IsoDate): string {
  return dayMonth.format(new Date(`${date}T00:00:00Z`))
}

/** "2026-11-14" → "Saturday, 14 November" */
export function formatLongDate(date: IsoDate): string {
  return weekdayLong.format(new Date(`${date}T00:00:00Z`))
}

/** "2026-11" → "November 2026" */
export function formatMonth(month: string): string {
  return monthYear.format(new Date(`${month}-01T00:00:00Z`))
}

/** Timestamp → "13:05" in the viewer's local time zone. */
export function formatTime(at: IsoDateTime): string {
  return time24.format(new Date(at))
}

/** The calendar date part of an ISO timestamp, as written by the server. */
export function datePart(at: IsoDateTime): IsoDate {
  return at.slice(0, 10)
}

/** "Today" / "Yesterday" / "12 Nov", relative to `today`. */
export function relativeDayLabel(date: IsoDate, today: IsoDate): string {
  const days = Math.round(
    (Date.parse(`${today}T00:00:00Z`) - Date.parse(`${date}T00:00:00Z`)) / 86_400_000,
  )
  if (days === 0) return 'Today'
  if (days === 1) return 'Yesterday'
  return formatDayMonth(date)
}
