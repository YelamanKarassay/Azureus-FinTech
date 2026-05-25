import type { BacktestStatus } from '../types/api'

const STATUS_STYLES: Record<string, string> = {
  queued: 'border-amber-200 bg-amber-50 text-amber-700',
  running: 'border-sky-200 bg-sky-50 text-sky-700',
  completed: 'border-emerald-200 bg-emerald-50 text-emerald-700',
  failed: 'border-rose-200 bg-rose-50 text-rose-700',
}

export function StatusBadge({ status }: { status: BacktestStatus }) {
  const style =
    STATUS_STYLES[status] ?? 'border-zinc-200 bg-zinc-100 text-zinc-700'
  return (
    <span
      className={`inline-flex items-center rounded-md border px-2.5 py-1 text-xs font-medium ${style}`}
    >
      {status}
    </span>
  )
}
