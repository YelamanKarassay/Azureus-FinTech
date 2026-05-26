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
  Object.entries(schema.properties ?? {}).forEach(([key, property]) => {
    if (key === 'sector_map') {
      params.sector_map = {}
      return
    }
    if (key === 'factor_weights') {
      params.factor_weights = DEFAULT_FACTOR_WEIGHTS
      return
    }
    if (property.default !== undefined && isJsonValue(property.default)) {
      params[key] = property.default
      return
    }
    if (property.enum?.[0] !== undefined && isJsonValue(property.enum[0])) {
      params[key] = property.enum[0]
      return
    }
    if (property.type === 'boolean') {
      params[key] = false
    }
  })
  if (hasSchemaProperty(schema, 'factor_weights')) {
    params.factor_weights = DEFAULT_FACTOR_WEIGHTS
  }

  const isStrategy2 = hasSchemaProperty(schema, 'training_warmup_years')
  return {
    start: isStrategy2 ? '2018-01-01' : '2026-04-01',
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
  const values = schemaProperty(schema, key)?.enum ?? fallback
  return values.map(String)
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

function isJsonValue(value: unknown): value is StrategyParamsPayload[string] {
  if (
    value === null ||
    typeof value === 'string' ||
    typeof value === 'number' ||
    typeof value === 'boolean'
  ) {
    return true
  }
  if (Array.isArray(value)) {
    return value.every(isJsonValue)
  }
  if (typeof value === 'object') {
    return Object.values(value).every(isJsonValue)
  }
  return false
}
