import { useState, type FormEvent } from 'react'
import { Link } from 'react-router'
import { api } from '../../api/client'
import type { ActivityItem, DashboardSummary, Task } from '../../api/types'
import { useCurrentUser } from '../../auth/context'
import { DomainBadge, SampleDataPill } from '../../components/ui/Badge'
import { BudgetList } from '../../components/ui/BudgetList'
import { Card } from '../../components/ui/Card'
import { Icon } from '../../components/ui/Icon'
import { PageState } from '../../components/ui/PageState'
import { StatCard } from '../../components/ui/StatCard'
import {
  datePart,
  formatDayMonth,
  formatLongDate,
  formatMoney,
  formatTime,
  relativeDayLabel,
} from '../../lib/format'
import { useApi } from '../../lib/useApi'

export function DashboardPage() {
  const state = useApi(api.getDashboard)
  return <PageState state={state}>{(data) => <Dashboard data={data} />}</PageState>
}

function greeting(hour: number): string {
  if (hour < 12) return 'Good morning'
  if (hour < 17) return 'Good afternoon'
  return 'Good evening'
}

function Dashboard({ data }: { data: DashboardSummary }) {
  const { week, last_weight: weight } = data
  const firstName = useCurrentUser().full_name.trim().split(/\s+/)[0]
  // Read the clock once on mount, not on every render (renders must be pure).
  const [hour] = useState(() => new Date().getHours())

  return (
    <div className="flex flex-col gap-7 px-10 pt-8 pb-12 max-sm:px-4">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="flex flex-col gap-1.5">
          <span className="text-sm text-muted">
            {formatLongDate(data.date)} · <SampleDataPill />
          </span>
          <h1 className="m-0 font-display text-[34px] font-semibold tracking-tight">
            {greeting(hour)}, {firstName}
          </h1>
        </div>
        <label className="flex h-11 min-w-64 items-center gap-2 rounded-xl border border-line bg-surface px-3.5 text-muted">
          <Icon name="search" size={16} />
          <span className="sr-only">Search your records</span>
          <input
            type="search"
            placeholder="Search expenses, memories, notes…"
            className="flex-1 border-none bg-transparent text-sm text-ink outline-none"
          />
        </label>
      </header>

      <QuickCapture />

      <section aria-label="This week" className="grid grid-cols-[repeat(auto-fit,minmax(210px,1fr))] gap-4">
        <StatCard
          label="Spent this week"
          value={formatMoney(week.spent)}
          hint={week.top_categories.map((c) => `${c.category} ${formatMoney(c.amount)}`).join(' · ')}
        />
        <StatCard label="DSA problems solved" value={week.dsa_solved} hint={`Goal ${week.dsa_goal} this week`} />
        <StatCard
          label="Gym sessions"
          value={
            <>
              {week.gym_sessions} <span className="text-lg text-muted">of {week.gym_goal}</span>
            </>
          }
          hint={week.last_gym && `Last: ${formatDayMonth(week.last_gym.occurred_on)}, ${week.last_gym.title}`}
        />
        <StatCard
          label="Last recorded weight"
          value={weight ? `${weight.kg} kg` : '—'}
          hint={weight && `${formatDayMonth(weight.recorded_on)} · ${weight.change_30d_kg} kg in 30 days`}
        />
      </section>

      <div className="flex flex-wrap items-start gap-5">
        <RecentActivity items={data.recent_activity} today={data.date} />
        <div className="flex min-w-0 flex-[2_1_300px] flex-col gap-5">
          <TodaysPlan initialTasks={data.tasks} />
          <Card title="November budgets">
            <BudgetList budgets={data.budgets} />
          </Card>
        </div>
      </div>
    </div>
  )
}

function QuickCapture() {
  const [text, setText] = useState('')
  const [notice, setNotice] = useState<string | null>(null)

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!text.trim()) return
    // Becomes a call to the assistant's extraction endpoint in Phase 3–4.
    setNotice(`Not saved: capture connects to the backend in Phase 3. You wrote: “${text.trim()}”`)
    setText('')
  }

  return (
    <section aria-label="Quick capture" className="flex flex-col gap-3.5 rounded-2xl border border-line bg-surface p-5">
      <form onSubmit={handleSubmit} className="flex flex-col gap-3.5">
        <label htmlFor="capture" className="text-[15px] font-semibold">
          Tell LifePilot what happened
        </label>
        <div className="flex flex-wrap gap-2.5">
          <input
            id="capture"
            type="text"
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="e.g. Spent ₹250 on lunch with Rutu, then went to the gym"
            className="h-12 flex-[1_1_320px] rounded-xl border border-line bg-canvas px-4 text-[15px] text-ink"
          />
          <button
            type="submit"
            className="flex h-12 cursor-pointer items-center gap-2 rounded-xl border-none bg-accent px-5 text-[15px] font-semibold text-on-accent hover:bg-accent-hover"
          >
            Save
            <Icon name="send" size={16} strokeWidth={2.2} />
          </button>
        </div>
      </form>
      <p role="status" className="m-0 text-[13px] text-muted">
        {notice ?? 'LifePilot extracts the details, saves them to the right place and confirms what it stored.'}
      </p>
    </section>
  )
}

function RecentActivity({ items, today }: { items: ActivityItem[]; today: string }) {
  // Group consecutive items by calendar day, keeping the server's newest-first order.
  const groups: { label: string; items: ActivityItem[] }[] = []
  for (const item of items) {
    const label = relativeDayLabel(datePart(item.occurred_at), today)
    const last = groups.at(-1)
    if (last?.label === label) last.items.push(item)
    else groups.push({ label, items: [item] })
  }

  return (
    <Card
      title="Recent activity"
      action={<span className="text-sm text-muted">Memory view arrives in Phase 4</span>}
      className="min-w-0 flex-[3_1_420px] gap-1"
    >
      {groups.map((group) => (
        <div key={group.label}>
          <h3 className="m-0 py-2 text-xs font-semibold tracking-wide text-muted uppercase">{group.label}</h3>
          <ul className="m-0 list-none p-0">
            {group.items.map((item) => (
              <li key={item.id} className="flex items-center gap-3.5 border-b border-line-soft py-3 last:border-b-0">
                <span className="w-12 text-[13px] text-muted">{formatTime(item.occurred_at)}</span>
                <div className="flex flex-1 flex-col gap-0.5">
                  <span className="text-[15px] font-medium">{item.title}</span>
                  <span className="text-xs text-muted">
                    {item.source === 'chat' ? 'From chat' : item.source === 'import' ? 'Imported' : 'Manual entry'} ·{' '}
                    {item.record_ref}
                  </span>
                </div>
                <DomainBadge domain={item.domain} />
              </li>
            ))}
          </ul>
        </div>
      ))}
      <Link to="/assistant" className="mt-2 text-sm font-medium text-accent hover:text-accent-hover">
        Ask the assistant about your history
      </Link>
    </Card>
  )
}

function TodaysPlan({ initialTasks }: { initialTasks: Task[] }) {
  const [tasks, setTasks] = useState(initialTasks)

  function toggle(id: string) {
    setTasks((current) => current.map((t) => (t.id === id ? { ...t, done: !t.done } : t)))
  }

  return (
    <Card title="Today's plan" className="gap-1.5">
      {tasks.map((task) => (
        <label
          key={task.id}
          className={`flex min-h-11 cursor-pointer items-center gap-3 text-[15px] ${task.done ? 'text-muted line-through' : ''}`}
        >
          <input
            type="checkbox"
            checked={task.done}
            onChange={() => toggle(task.id)}
            className="size-4.5 accent-accent"
          />
          {task.title}
        </label>
      ))}
    </Card>
  )
}
