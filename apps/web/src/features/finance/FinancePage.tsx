import { api } from '../../api/client'
import type { Borrowing, CategoryAmount, FinanceMonth, Transaction } from '../../api/types'
import { SampleDataPill } from '../../components/ui/Badge'
import { BudgetList } from '../../components/ui/BudgetList'
import { Card } from '../../components/ui/Card'
import { PageState } from '../../components/ui/PageState'
import { StatCard } from '../../components/ui/StatCard'
import { formatDayMonth, formatMoney, formatMonth, ratio } from '../../lib/format'
import { useApi } from '../../lib/useApi'

export function FinancePage() {
  const state = useApi(api.getFinanceMonth)
  return <PageState state={state}>{(data) => <Finance data={data} />}</PageState>
}

function Finance({ data }: { data: FinanceMonth }) {
  const owedToMe = data.borrowings.filter((b) => b.direction === 'owed_to_me')

  return (
    <div className="flex flex-col gap-6 px-10 pt-8 pb-12 max-sm:px-4">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex flex-col gap-1.5">
          <h1 className="m-0 font-display text-[32px] font-semibold tracking-tight">Finance</h1>
          <span className="text-sm text-muted">
            {formatMonth(data.month)} · <SampleDataPill />
          </span>
        </div>
        <button
          type="button"
          disabled
          title="Adding expenses arrives with the Finance API (Phase 5)"
          className="h-11 rounded-xl border-none bg-accent px-4.5 text-sm font-semibold text-on-accent disabled:cursor-not-allowed disabled:opacity-60"
        >
          Add expense
        </button>
      </header>

      <section aria-label="Month summary" className="grid grid-cols-[repeat(auto-fit,minmax(200px,1fr))] gap-4">
        <StatCard label="Spent" value={formatMoney(data.spent)} hint={`${data.transaction_count} transactions`} />
        <StatCard label="Income" value={formatMoney(data.income)} hint={data.income_note} />
        <StatCard
          label="Left this month"
          value={formatMoney(data.net)}
          hint="Income minus spending"
          valueClassName="text-success"
        />
        <StatCard
          label="Owed to you"
          value={formatMoney(data.owed_to_me)}
          hint={owedToMe.map((b) => `${b.person} · ${b.entries.length} entries`).join(', ')}
        />
      </section>

      <div className="flex flex-wrap items-start gap-5">
        <Card title="Spending by category" className="min-w-0 flex-[1_1_340px]">
          <CategoryBars categories={data.by_category} />
        </Card>
        <div className="flex min-w-0 flex-[1_1_300px] flex-col gap-5">
          <Card title="Budgets">
            <BudgetList budgets={data.budgets} />
          </Card>
          <Card title="Borrowings" className="gap-3">
            <BorrowingList borrowings={data.borrowings} />
          </Card>
        </div>
      </div>

      <Card
        title="This week"
        action={
          <span className="text-sm text-muted">
            {formatDayMonth(data.week.start)} – {formatDayMonth(data.week.end)} · {formatMoney(data.week.total)}
          </span>
        }
        className="gap-3"
      >
        <TransactionTable transactions={data.week.transactions} />
      </Card>
    </div>
  )
}

function CategoryBars({ categories }: { categories: CategoryAmount[] }) {
  // Bars are relative to the largest category, which fills the track.
  const largest = categories.reduce((max, c) => (Number(c.amount) > Number(max) ? c.amount : max), '0')
  return (
    <ul className="m-0 grid list-none grid-cols-[96px_minmax(0,1fr)_80px] items-center gap-x-3 gap-y-3.5 p-0 text-sm">
      {categories.map((c) => (
        <li key={c.category} className="contents">
          <span className="font-medium">{c.category}</span>
          <div aria-hidden="true" className="h-3 rounded bg-line-soft">
            <div className="h-3 rounded bg-accent" style={{ width: `${ratio(c.amount, largest) * 100}%` }} />
          </div>
          <span className="text-right tabular-nums">{formatMoney(c.amount)}</span>
        </li>
      ))}
    </ul>
  )
}

function BorrowingList({ borrowings }: { borrowings: Borrowing[] }) {
  return (
    <ul className="m-0 list-none p-0">
      {borrowings.map((b) => {
        const owedToMe = b.direction === 'owed_to_me'
        return (
          <li
            key={b.id}
            className="flex items-center justify-between gap-3 border-b border-line-soft py-2 text-sm last:border-b-0"
          >
            <div className="flex flex-col gap-0.5">
              <span className="font-medium">{owedToMe ? `${b.person} owes you` : `You owe ${b.person}`}</span>
              <span className="text-xs text-muted">
                {b.entries.map((e) => `${formatMoney(e.amount)} on ${formatDayMonth(e.on)}`).join(' · ')}
              </span>
            </div>
            <span className={`font-semibold ${owedToMe ? 'text-success' : 'text-warning'}`}>{formatMoney(b.total)}</span>
          </li>
        )
      })}
    </ul>
  )
}

const SOURCE_LABEL: Record<Transaction['source'], string> = { chat: 'Chat', manual: 'Manual', import: 'Import' }

function TransactionTable({ transactions }: { transactions: Transaction[] }) {
  const cell = 'border-b border-line-soft px-2 py-3'
  const head = 'border-b border-line px-2 py-2.5 text-xs font-semibold tracking-wide text-muted uppercase'
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[620px] border-collapse text-left text-sm">
        <thead>
          <tr>
            <th scope="col" className={head}>Date</th>
            <th scope="col" className={head}>Description</th>
            <th scope="col" className={head}>Category</th>
            <th scope="col" className={head}>Added via</th>
            <th scope="col" className={`${head} text-right`}>Amount</th>
          </tr>
        </thead>
        <tbody>
          {transactions.map((t) => (
            <tr key={t.id} className="[&:last-child>td]:border-b-0">
              <td className={`${cell} text-muted`}>{formatDayMonth(t.date)}</td>
              <td className={`${cell} font-medium`}>{t.description}</td>
              <td className={cell}>{t.category}</td>
              <td className={`${cell} text-muted`}>{SOURCE_LABEL[t.source]}</td>
              <td className={`${cell} text-right font-medium tabular-nums`}>{formatMoney(t.amount)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
