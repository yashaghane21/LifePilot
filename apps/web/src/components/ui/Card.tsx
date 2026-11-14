import { useId, type ReactNode } from 'react'

interface CardProps {
  title?: string
  /** Right-aligned element in the header row, e.g. a link. */
  action?: ReactNode
  className?: string
  children: ReactNode
}

/** White panel with an optional heading; renders as a labelled <section>. */
export function Card({ title, action, className = '', children }: CardProps) {
  const headingId = useId()
  return (
    <section
      aria-labelledby={title ? headingId : undefined}
      className={`flex flex-col gap-4 rounded-2xl border border-line bg-surface p-6 ${className}`}
    >
      {(title || action) && (
        <div className="flex flex-wrap items-center justify-between gap-2">
          {title && (
            <h2 id={headingId} className="m-0 font-display text-xl font-semibold">
              {title}
            </h2>
          )}
          {action}
        </div>
      )}
      {children}
    </section>
  )
}
