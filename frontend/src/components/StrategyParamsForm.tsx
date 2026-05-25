import type { FormEvent } from 'react'
import type {
  BacktestFormValues,
  JsonSchema,
  JsonValue,
  StrategyParamsPayload,
} from '../types/api'
import {
  enumOptions,
  hasSchemaProperty,
  numberMaximum,
  numberMinimum,
} from '../utils/defaultFormValues'
import { formatCurrency } from '../utils/format'

const DEFAULT_FACTOR_WEIGHTS: Record<string, number> = {
  value: 0.25,
  quality: 0.25,
  momentum: 0.25,
  low_vol: 0.25,
}

interface StrategyParamsFormProps {
  values: BacktestFormValues
  schema: JsonSchema
  isSubmitting: boolean
  onChange: (values: BacktestFormValues) => void
  onSubmit: () => void
}

export function StrategyParamsForm({
  values,
  schema,
  isSubmitting,
  onChange,
  onSubmit,
}: StrategyParamsFormProps) {
  const params = values.params
  const universeId = stringParam(params.universe_id, 'HSI')
  const rebalanceFrequency = stringParam(params.rebalance_frequency, 'monthly')
  const nLong = numberParam(params.n_long, 20)
  const weightingScheme = stringParam(params.weighting_scheme, 'equal')
  const liquidityThreshold = numberParam(params.liquidity_threshold_usd, 1_000_000)
  const sectorNeutral = booleanParam(params.sector_neutral, true)
  const factorWeights = numberRecordParam(
    params.factor_weights,
    DEFAULT_FACTOR_WEIGHTS,
  )

  function update(valuesPatch: Partial<BacktestFormValues>) {
    onChange({ ...values, ...valuesPatch })
  }

  function updateParams(paramsPatch: Partial<StrategyParamsPayload>) {
    const nextParams: StrategyParamsPayload = { ...params }
    Object.entries(paramsPatch).forEach(([key, value]) => {
      if (value !== undefined) {
        nextParams[key] = value
      }
    })
    onChange({ ...values, params: nextParams })
  }

  function updateFactorWeight(family: string, value: number) {
    updateParams({
      factor_weights: {
        ...factorWeights,
        [family]: value,
      },
    })
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    onSubmit()
  }

  return (
    <form className="space-y-5" onSubmit={handleSubmit}>
      <div className="grid gap-4 md:grid-cols-2">
        <label className="space-y-2">
          <span className="text-sm font-medium text-zinc-700">Start date</span>
          <input
            className="w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm"
            type="date"
            value={values.start}
            onChange={(event) => update({ start: event.target.value })}
          />
        </label>
        <label className="space-y-2">
          <span className="text-sm font-medium text-zinc-700">End date</span>
          <input
            className="w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm"
            type="date"
            value={values.end}
            onChange={(event) => update({ end: event.target.value })}
          />
        </label>
        <label className="space-y-2">
          <span className="text-sm font-medium text-zinc-700">
            Initial capital
          </span>
          <input
            className="w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm"
            type="number"
            min={100_000}
            step={100_000}
            value={values.initial_capital}
            onChange={(event) =>
              update({ initial_capital: Number(event.target.value) })
            }
          />
          <span className="block text-xs text-zinc-500">
            {formatCurrency(values.initial_capital)}
          </span>
        </label>
        <label className="space-y-2">
          <span className="text-sm font-medium text-zinc-700">Random seed</span>
          <input
            className="w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm"
            type="number"
            min={0}
            value={values.random_seed}
            onChange={(event) =>
              update({ random_seed: Number(event.target.value) })
            }
          />
        </label>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        {hasSchemaProperty(schema, 'universe_id') && (
          <label className="space-y-2">
            <span className="text-sm font-medium text-zinc-700">Universe</span>
            <input
              className="w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm"
              value={universeId}
              onChange={(event) =>
                updateParams({ universe_id: event.target.value })
              }
            />
          </label>
        )}
        {hasSchemaProperty(schema, 'rebalance_frequency') && (
          <label className="space-y-2">
            <span className="text-sm font-medium text-zinc-700">
              Rebalance cadence
            </span>
            <select
              className="w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm"
              value={rebalanceFrequency}
              onChange={(event) =>
                updateParams({ rebalance_frequency: event.target.value })
              }
            >
              {enumOptions(schema, 'rebalance_frequency', [
                'monthly',
                'quarterly',
              ]).map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </label>
        )}
        {hasSchemaProperty(schema, 'n_long') && (
          <label className="space-y-2">
            <span className="text-sm font-medium text-zinc-700">
              Long positions
            </span>
            <input
              className="w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm"
              type="number"
              min={numberMinimum(schema, 'n_long', 10)}
              max={numberMaximum(schema, 'n_long', 40)}
              value={nLong}
              onChange={(event) =>
                updateParams({ n_long: Number(event.target.value) })
              }
            />
          </label>
        )}
        {hasSchemaProperty(schema, 'weighting_scheme') && (
          <label className="space-y-2">
            <span className="text-sm font-medium text-zinc-700">
              Weighting scheme
            </span>
            <select
              className="w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm"
              value={weightingScheme}
              onChange={(event) =>
                updateParams({ weighting_scheme: event.target.value })
              }
            >
              {enumOptions(schema, 'weighting_scheme', [
                'equal',
                'score_weighted',
              ]).map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        {hasSchemaProperty(schema, 'liquidity_threshold_usd') && (
          <label className="space-y-2">
            <span className="text-sm font-medium text-zinc-700">
              Liquidity threshold
            </span>
            <input
              className="w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm"
              type="number"
              min={0}
              step={100_000}
              value={liquidityThreshold}
              onChange={(event) =>
                updateParams({
                  liquidity_threshold_usd: Number(event.target.value),
                })
              }
            />
            <span className="block text-xs text-zinc-500">
              {formatCurrency(liquidityThreshold)}
            </span>
          </label>
        )}
        {hasSchemaProperty(schema, 'sector_neutral') && (
          <label className="flex items-center gap-3 rounded-md border border-zinc-200 bg-zinc-50 px-3 py-2">
            <input
              type="checkbox"
              className="h-4 w-4 rounded border-zinc-300"
              checked={sectorNeutral}
              onChange={(event) =>
                updateParams({ sector_neutral: event.target.checked })
              }
            />
            <span className="text-sm font-medium text-zinc-700">
              Sector-neutral ranking
            </span>
          </label>
        )}
      </div>

      {hasSchemaProperty(schema, 'factor_weights') && (
        <div>
          <p className="mb-3 text-sm font-medium text-zinc-700">
            Family weights
          </p>
          <div className="grid gap-3 md:grid-cols-4">
            {Object.entries(factorWeights).map(([family, value]) => (
              <label key={family} className="space-y-2">
                <span className="text-xs font-medium uppercase text-zinc-500">
                  {family.replace('_', ' ')}
                </span>
                <input
                  className="w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm"
                  type="number"
                  min={0}
                  max={1}
                  step={0.05}
                  value={value}
                  onChange={(event) =>
                    updateFactorWeight(family, Number(event.target.value))
                  }
                />
              </label>
            ))}
          </div>
        </div>
      )}

      <button
        type="submit"
        disabled={isSubmitting}
        className="w-full rounded-md bg-zinc-950 px-4 py-3 text-sm font-semibold text-white hover:bg-zinc-800 disabled:cursor-not-allowed disabled:bg-zinc-400"
      >
        {isSubmitting ? 'Queueing backtest' : 'Run backtest'}
      </button>
    </form>
  )
}

function stringParam(value: JsonValue | undefined, fallback: string): string {
  return typeof value === 'string' ? value : fallback
}

function numberParam(value: JsonValue | undefined, fallback: number): number {
  return typeof value === 'number' ? value : fallback
}

function booleanParam(value: JsonValue | undefined, fallback: boolean): boolean {
  return typeof value === 'boolean' ? value : fallback
}

function numberRecordParam(
  value: JsonValue | undefined,
  fallback: Record<string, number>,
): Record<string, number> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return fallback
  }
  const entries = Object.entries(value).filter(
    (entry): entry is [string, number] => typeof entry[1] === 'number',
  )
  return entries.length > 0 ? Object.fromEntries(entries) : fallback
}
