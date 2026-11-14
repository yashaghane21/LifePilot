import type { Budget } from '../../api/types'
import { formatMoney, ratio } from '../../lib/format'

/** Budgets with a progress bar each; an over-limit budget is called out in text, not colour alone. */
export function BudgetList({ budgets }: { budgets: Budget[] }) {
  return (
    <div className="flex flex-col gap-4">
      {budgets.map((budget) => {
        const over = Number(budget.spent) > Number(budget.limit)
        const percent = Math.round(ratio(budget.spent, budget.limit) * 100)
        return (
          <div key={budget.category} className="flex flex-col gap-2">
            <div className="flex justify-between gap-2 text-sm">
              <span className="font-medium">{budget.category}</span>
              <span className={over ? 'font-semibold text-warning' : 'text-muted'}>
                {formatMoney(budget.spent)} of {formatMoney(budget.limit)}
                {over && ' · over'}
              </span>
            </div>
            <div
              role="progressbar"
              aria-label={`${budget.category} budget used`}
              aria-valuenow={percent}
              aria-valuemin={0}
              aria-valuemax={100}
              className="h-2 rounded-full bg-line-soft"
            >
              <div
                className={`h-2 rounded-full ${over ? 'bg-warning-strong' : 'bg-accent'}`}
                style={{ width: `${percent}%` }}
              />
            </div>
          </div>
        )
      })}
    </div>
  )
}
