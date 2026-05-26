import { useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from '@tanstack/react-router'
import { useCreateBacktest } from '../api/backtests'
import { useStrategy } from '../api/catalog'
import { StrategyParamsForm } from '../components/StrategyParamsForm'
import { useBacktestStore } from '../stores/backtestStore'
import type { BacktestFormValues } from '../types/api'
import { defaultFormValues } from '../utils/defaultFormValues'

export function StrategyDetailPage() {
  const { strategyId } = useParams({ from: '/strategies/$strategyId' })
  const navigate = useNavigate()
  const strategy = useStrategy(strategyId)
  const createBacktest = useCreateBacktest()
  const setLatestJobId = useBacktestStore((state) => state.setLatestJobId)
  const defaultValues = useMemo(
    () =>
      strategy.data
        ? defaultFormValues(strategy.data.params_schema)
        : undefined,
    [strategy.data],
  )
  const [formValues, setFormValues] = useState<BacktestFormValues | null>(
    null,
  )
  const values = formValues ?? defaultValues

  async function submitBacktest() {
    if (!strategy.data || !values) return
    const dataProvider =
      strategy.data.id === 'gbm_factors_v1' ? 'public_free' : 'yfinance'
    const response = await createBacktest.mutateAsync({
      strategy_id: strategy.data.id,
      params: values.params,
      start: values.start,
      end: values.end,
      initial_capital: values.initial_capital,
      data_provider: dataProvider,
      random_seed: values.random_seed,
    })
    setLatestJobId(response.job_id)
    await navigate({
      to: '/backtests/$jobId',
      params: { jobId: response.job_id },
    })
  }

  return (
    <main className="mx-auto max-w-7xl px-5 py-8">
      <div className="mb-5">
        <Link to="/" className="text-sm font-medium text-teal-700">
          Back to strategies
        </Link>
      </div>

      {strategy.isPending && (
        <p className="rounded-md border border-zinc-200 bg-white px-4 py-5 text-sm text-zinc-500">
          Loading strategy
        </p>
      )}

      {strategy.isError && (
        <p className="rounded-md border border-rose-200 bg-rose-50 px-4 py-5 text-sm text-rose-700">
          {strategy.error.message}
        </p>
      )}

      {strategy.data && values && (
        <div className="grid gap-6 xl:grid-cols-[1fr_420px]">
          <section>
            <p className="font-mono text-xs uppercase text-zinc-500">
              {strategy.data.id}
            </p>
            <h1 className="mt-2 text-3xl font-semibold tracking-tight text-zinc-950">
              {strategy.data.name}
            </h1>
            <p className="mt-3 max-w-3xl text-zinc-600">
              {strategy.data.description}
            </p>

            <div className="mt-6 rounded-md border border-zinc-200 bg-white">
              <div className="border-b border-zinc-200 px-4 py-3">
                <h2 className="font-semibold">Parameter schema</h2>
              </div>
              <div className="grid gap-3 p-4 md:grid-cols-2">
                {Object.entries(strategy.data.params_schema.properties ?? {}).map(
                  ([key, property]) => (
                    <div
                      key={key}
                      className="rounded-md border border-zinc-200 bg-zinc-50 px-3 py-2"
                    >
                      <p className="font-mono text-xs text-zinc-500">{key}</p>
                      <p className="mt-1 text-sm font-medium text-zinc-800">
                        {property.title ?? key}
                      </p>
                    </div>
                  ),
                )}
              </div>
            </div>
          </section>

          <section className="rounded-md border border-zinc-200 bg-white">
            <div className="border-b border-zinc-200 px-4 py-3">
              <h2 className="font-semibold">Run backtest</h2>
            </div>
            <div className="p-4">
              <StrategyParamsForm
                values={values}
                schema={strategy.data.params_schema}
                isSubmitting={createBacktest.isPending}
                onChange={setFormValues}
                onSubmit={submitBacktest}
              />
              {createBacktest.isError && (
                <p className="mt-4 rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
                  {createBacktest.error.message}
                </p>
              )}
            </div>
          </section>
        </div>
      )}
    </main>
  )
}
