import type { Domain } from '../../api/types'

const DOMAIN_STYLES: Record<Domain, { label: string; className: string }> = {
  finance: { label: 'Finance', className: 'bg-accent-soft text-accent-hover' },
  personal: { label: 'Personal', className: 'bg-line-soft text-ink-soft' },
  study: { label: 'Study', className: 'bg-success-soft text-success' },
  fitness: { label: 'Fitness', className: 'bg-warning-soft text-warning' },
}

export function DomainBadge({ domain }: { domain: Domain }) {
  const { label, className } = DOMAIN_STYLES[domain]
  return <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${className}`}>{label}</span>
}

/** Marks screens that are still showing mock data, so nobody mistakes it for real records. */
export function SampleDataPill() {
  return (
    <span className="rounded-full bg-warning-soft px-2 py-0.5 text-xs font-semibold text-warning">
      Sample data
    </span>
  )
}
