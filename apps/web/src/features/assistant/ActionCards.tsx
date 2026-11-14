// Cards for tool results and approvals, from the approved assistant design. Not used yet:
// they get wired to real data when tool calling arrives (Phase 3.5).
import { Icon } from '../../components/ui/Icon'

export interface ToolResultCardProps {
  tool: string
  status: 'verified' | 'failed'
  fields: { label: string; value: string }[]
  recordRef: string
}

export function ToolResultCard({ tool, status, fields, recordRef }: ToolResultCardProps) {
  const verified = status === 'verified'
  return (
    <div className="overflow-hidden rounded-2xl border border-line">
      <div
        className={`flex items-center justify-between gap-3 px-4 py-2.5 text-[13px] font-semibold ${
          verified ? 'bg-success-soft text-success' : 'bg-warning-soft text-warning'
        }`}
      >
        <span className="flex items-center gap-2">
          <Icon name={verified ? 'check' : 'warning'} size={16} strokeWidth={2.5} />
          {verified ? 'Saved and verified' : 'Could not verify'}
        </span>
        <span className="font-mono text-xs font-medium">{tool}</span>
      </div>
      <dl className="m-0 grid grid-cols-[repeat(auto-fit,minmax(110px,1fr))] gap-3 px-4 py-3.5">
        {fields.map((field) => (
          <div key={field.label} className="flex flex-col gap-0.5">
            <dt className="text-xs text-muted">{field.label}</dt>
            <dd className="m-0 text-[15px] font-semibold">{field.value}</dd>
          </div>
        ))}
      </dl>
      <p className="m-0 px-4 pb-3 text-xs text-muted">Stored as {recordRef} · read back from the database</p>
    </div>
  )
}

export interface ApprovalCardProps {
  summary: string
  confirmLabel: string
  status: 'pending' | 'approved' | 'cancelled'
  onDecide: (decision: 'approved' | 'cancelled') => void
}

export function ApprovalCard({ summary, confirmLabel, status, onDecide }: ApprovalCardProps) {
  const pending = status === 'pending'
  return (
    <div className="flex flex-col gap-3 rounded-2xl border border-warning-line p-4">
      <span className="flex items-center gap-2 text-sm font-semibold text-warning">
        <Icon name="warning" />
        {pending ? 'Needs your approval' : status === 'approved' ? 'Approved' : 'Cancelled'}
      </span>
      <p className="m-0 text-[15px] leading-7">{summary}</p>
      {pending && (
        <div className="flex flex-wrap gap-2.5">
          <button
            type="button"
            onClick={() => onDecide('cancelled')}
            className="h-10 cursor-pointer rounded-full border border-line bg-transparent px-4 text-sm font-semibold text-ink hover:bg-bubble"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={() => onDecide('approved')}
            className="h-10 cursor-pointer rounded-full border-none bg-danger px-4 text-sm font-semibold text-white hover:opacity-90"
          >
            {confirmLabel}
          </button>
        </div>
      )}
    </div>
  )
}
