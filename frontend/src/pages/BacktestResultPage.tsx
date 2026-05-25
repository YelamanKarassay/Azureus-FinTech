import { Link, useParams } from '@tanstack/react-router'
import { useBacktestResult, useBacktestStatus } from '../api/backtests'
import { ResultDashboard } from '../components/charts/ResultDashboard'
import { StatusBadge } from '../components/StatusBadge'
import { formatDate } from '../utils/format'

export function BacktestResultPage() {
  const { jobId } = useParams({ from: '/backtests/$jobId' })
  const status = useBacktestStatus(jobId)
  const isCompleted = status.data?.status === 'completed'
  const result = useBacktestResult(jobId, isCompleted)

  return (
    <main className="mx-auto max-w-7xl px-5 py-8">
      <div className="mb-5">
        <Link to="/" className="text-sm font-medium text-teal-700">
          Back to strategies
        </Link>
      </div>

      <section className="mb-6 rounded-md border border-zinc-200 bg-white px-4 py-4">
        <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div>
            <p className="font-mono text-xs uppercase text-zinc-500">
              {jobId.slice(0, 8)}
            </p>
            <h1 className="mt-2 text-2xl font-semibold tracking-tight text-zinc-950">
              Backtest job
            </h1>
            <p className="mt-1 text-sm text-zinc-500">
              Created {formatDate(status.data?.created_at)} · provider{' '}
              {status.data?.data_provider ?? '—'}
            </p>
          </div>
          <StatusBadge status={status.data?.status ?? 'loading'} />
        </div>

        {status.data?.status === 'failed' && (
          <p className="mt-4 rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
            {status.data.error_message ?? 'Backtest failed.'}
          </p>
        )}
      </section>

      {(status.isPending || status.data?.status === 'queued') && (
        <ProgressPanel title="Queued" body="Waiting for an RQ worker to pick up this job." />
      )}

      {status.data?.status === 'running' && (
        <ProgressPanel title="Running" body="The worker is executing the backtest." />
      )}

      {isCompleted && result.isPending && (
        <ProgressPanel title="Loading result" body="Fetching persisted analytics." />
      )}

      {result.isError && (
        <p className="rounded-md border border-rose-200 bg-rose-50 px-4 py-5 text-sm text-rose-700">
          {result.error.message}
        </p>
      )}

      {result.data && <ResultDashboard result={result.data} />}
    </main>
  )
}

function ProgressPanel({ title, body }: { title: string; body: string }) {
  return (
    <section className="rounded-md border border-zinc-200 bg-white px-4 py-5">
      <p className="font-semibold text-zinc-900">{title}</p>
      <p className="mt-1 text-sm text-zinc-500">{body}</p>
    </section>
  )
}
