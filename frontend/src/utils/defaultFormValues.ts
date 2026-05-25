import type {
  BacktestFormValues,
  JsonSchema,
  StrategyParamsPayload,
} from '../types/api'

const DEFAULT_FACTOR_WEIGHTS = {
  value: 0.25,
  quality: 0.25,
  momentum: 0.25,
  low_vol: 0.25,
}

export function defaultFormValues(schema: JsonSchema): BacktestFormValues {
  const params: StrategyParamsPayload = {}
  if (hasSchemaProperty(schema, 'universe_id')) {
    params.universe_id = stringDefault(schema, 'universe_id', 'HSI')
  }
  if (hasSchemaProperty(schema, 'rebalance_frequency')) {
    params.rebalance_frequency = enumDefault(
      schema,
      'rebalance_frequency',
      'monthly',
    )
  }
  if (hasSchemaProperty(schema, 'n_long')) {
    params.n_long = numberDefault(schema, 'n_long', 20)
  }
  if (hasSchemaProperty(schema, 'sector_neutral')) {
    params.sector_neutral = booleanDefault(schema, 'sector_neutral', true)
  }
  if (hasSchemaProperty(schema, 'factor_weights')) {
    params.factor_weights = DEFAULT_FACTOR_WEIGHTS
  }
  if (hasSchemaProperty(schema, 'weighting_scheme')) {
    params.weighting_scheme = enumDefault(schema, 'weighting_scheme', 'equal')
  }
  if (hasSchemaProperty(schema, 'liquidity_threshold_usd')) {
    params.liquidity_threshold_usd = numberDefault(
      schema,
      'liquidity_threshold_usd',
      1_000_000,
    )
  }
  if (hasSchemaProperty(schema, 'sector_map')) {
    params.sector_map = {}
  }

  return {
    start: '2026-04-01',
    end: '2026-05-22',
    initial_capital: 1_000_000,
    random_seed: 0,
    params,
  }
}

export function hasSchemaProperty(schema: JsonSchema, key: string) {
  return schemaProperty(schema, key) !== undefined
}

export function enumOptions(
  schema: JsonSchema,
  key: string,
  fallback: string[],
) {
  return schemaProperty(schema, key)?.enum ?? fallback
}

export function numberMinimum(schema: JsonSchema, key: string, fallback: number) {
  return schemaProperty(schema, key)?.minimum ?? fallback
}

export function numberMaximum(schema: JsonSchema, key: string, fallback: number) {
  return schemaProperty(schema, key)?.maximum ?? fallback
}

function schemaProperty(schema: JsonSchema, key: string) {
  return schema.properties?.[key]
}

function stringDefault(schema: JsonSchema, key: string, fallback: string) {
  const value = schemaProperty(schema, key)?.default
  return typeof value === 'string' ? value : fallback
}

function numberDefault(schema: JsonSchema, key: string, fallback: number) {
  const value = schemaProperty(schema, key)?.default
  return typeof value === 'number' ? value : fallback
}

function booleanDefault(schema: JsonSchema, key: string, fallback: boolean) {
  const value = schemaProperty(schema, key)?.default
  return typeof value === 'boolean' ? value : fallback
}

function enumDefault<T extends string>(schema: JsonSchema, key: string, fallback: T) {
  const value = schemaProperty(schema, key)?.default
  return typeof value === 'string' ? (value as T) : fallback
}
