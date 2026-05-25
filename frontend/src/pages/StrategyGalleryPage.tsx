import { Link } from '@tanstack/react-router'
import { useBacktests } from '../api/backtests'
import { useFeatures, useStrategies } from '../api/catalog'
import { StatusBadge } from '../components/StatusBadge'
import { formatDate } from '../utils/format'

export function StrategyGalleryPage() {
  const strategies = useStrategies()
  const features = useFeatures()
  const backtests = useBacktests()

  return (
    <main className="mx-auto max-w-7xl px-5 py-8">
      <div className="mb-6 grid gap-5 lg:grid-cols-[1.5fr_1fr]">
        <section>
          <p className="text-sm font-medium uppercase text-teal-700">
            Phase 3 local E2E
          </p>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight text-zinc-950">
            Strategy workbench
          </h1>
          <p className="mt-3 max-w-3xl text-zinc-600">
            Browse registered strategies, inspect their inputs, launch an async
            backtest, and review persisted result analytics from the local job
            queue path.
          </p>
        </section>
        <section className="rounded-md border border-zinc-200 bg-white px-4 py-3">
          <p className="text-sm font-medium text-zinc-700">Feature catalog</p>
          <div className="mt-3 flex flex-wrap gap-2">
            {(features.data ?? []).slice(0, 12).map((feature) => (
              <span
                key={feature.name}
                className="rounded-md border border-zinc-200 bg-zinc-50 px-2 py-1 font-mono text-xs text-zinc-700"
              >
                {feature.name}
              </span>
            ))}
            {features.isPending && (
              <span className="text-sm text-zinc-500">Loading features</span>
            )}
          </div>
        </section>
      </div>

      <div className="grid gap-6 xl:grid-cols-[1fr_360px]">
        <section className="rounded-md border border-zinc-200 bg-white">
          <div className="border-b border-zinc-200 px-4 py-3">
            <h2 className="font-semibold">Registered strategies</h2>
          </div>
          <div className="divide-y divide-zinc-100">
            {(strategies.data ?? []).map((strategy) => (
              <Link
                key={strategy.id}
                to="/strategies/$strategyId"
                params={{ strategyId: strategy.id }}
                className="block px-4 py-4 hover:bg-zinc-50"
              >
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <p className="font-semibold text-zinc-950">
                      {strategy.name}
                    </p>
                    <p className="mt-1 text-sm text-zinc-600">
                      {strategy.description}
                    </p>
                  </div>
                  <span className="rounded-md border border-zinc-200 px-2 py-1 font-mono text-xs text-zinc-500">
                    {strategy.id}
                  </span>
                </div>
              </Link>
            ))}
            {strategies.isPending && (
              <p className="px-4 py-5 text-sm text-zinc-500">
                Loading strategies
              </p>
            )}
          </div>
        </section>

        <section className="rounded-md border border-zinc-200 bg-white">
          <div className="border-b border-zinc-200 px-4 py-3">
            <h2 className="font-semibold">Recent jobs</h2>
          </div>
          <div className="divide-y divide-zinc-100">
            {(backtests.data ?? []).slice(0, 8).map((job) => (
              <Link
                key={job.job_id}
                to="/backtests/$jobId"
                params={{ jobId: job.job_id }}
                className="block px-4 py-3 hover:bg-zinc-50"
              >
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="font-mono text-xs text-zinc-500">
                      {job.job_id.slice(0, 8)}
                    </p>
                    <p className="mt-1 text-sm text-zinc-700">
                      {job.strategy_id ?? 'unknown'}
                    </p>
                    <p className="mt-1 text-xs text-zinc-500">
                      {formatDate(job.created_at)}
                    </p>
                  </div>
                  <StatusBadge status={job.status} />
                </div>
              </Link>
            ))}
            {!backtests.isPending && (backtests.data ?? []).length === 0 && (
              <p className="px-4 py-5 text-sm text-zinc-500">
                No backtest jobs yet.
              </p>
            )}
          </div>
        </section>
      </div>
    </main>
  )
}
