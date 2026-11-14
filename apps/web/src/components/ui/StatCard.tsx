import type { ReactNode } from 'react'

interface StatCardProps {
  label: string
  value: ReactNode
  hint?: ReactNode
  valueClassName?: string
}

export function StatCard({ label, value, hint, valueClassName = '' }: StatCardProps) {
  return (
    <div className="flex flex-col gap-2 rounded-2xl border border-line bg-surface p-5">
      <span className="text-[13px] font-medium text-muted">{label}</span>
      <span className={`font-display text-3xl font-semibold ${valueClassName}`}>{value}</span>
      {hint && <span className="text-[13px] text-muted">{hint}</span>}
    </div>
  )
}
