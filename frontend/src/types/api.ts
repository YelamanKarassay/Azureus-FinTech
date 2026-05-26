export interface StrategySummary {
  id: string
  name: string
  description: string
}

export interface JsonSchemaProperty {
  title?: string
  description?: string
  default?: unknown
  minimum?: number
  maximum?: number
  enum?: JsonValue[]
  type?: string
}

export interface JsonSchema {
  title?: string
  properties?: Record<string, JsonSchemaProperty>
}

export interface StrategyDetail extends StrategySummary {
  params_schema: JsonSchema
}

export interface FeatureSummary {
  name: string
  description: string
  family: string
  requires_metrics: string[]
  requires_lookback_days: number
}

export type BacktestStatus =
  | 'queued'
  | 'running'
  | 'completed'
  | 'failed'
  | string

export interface BacktestCreateRequest {
  strategy_id: string
  params: StrategyParamsPayload
  start: string
  end: string
  initial_capital: number
  data_provider: 'yfinance' | 'public_free'
  random_seed: number
}

export interface BacktestCreateResponse {
  job_id: string
  status: BacktestStatus
}

export interface BacktestStatusResponse {
  job_id: string
  strategy_id: string | null
  job_type: string
  status: BacktestStatus
  params: Record<string, unknown>
  data_provider: string
  created_at: string
  started_at: string | null
  completed_at: string | null
  error_message: string | null
}

export interface EquityCurveRow {
  date: string
  cash?: number
  total_value: number
  daily_return?: number
}

export interface HoldingRow {
  date: string
  ticker: string
  weight: number
  shares?: number
  last_price?: number
  market_value?: number
}

export interface TradeRow {
  ticker: string
  executed_at?: string
  shares: number
  fill_price?: number
  gross_notional?: number
  total_cost?: number
  commission?: number
  stamp_duty?: number
  sfc_levy?: number
  hkex_fee?: number
  ccass_fee?: number
  slippage?: number
  net_cash_change?: number
}

export interface BacktestResultResponse {
  job_id: string
  summary: Record<string, number | string | null>
  equity_curve: EquityCurveRow[]
  holdings: HoldingRow[]
  trades: TradeRow[]
  diagnostics?: Record<string, JsonValue> | null
}

export type JsonValue =
  | string
  | number
  | boolean
  | null
  | JsonValue[]
  | { [key: string]: JsonValue }

export type StrategyParamsPayload = Record<string, JsonValue>

export interface BacktestFormValues {
  start: string
  end: string
  initial_capital: number
  random_seed: number
  params: StrategyParamsPayload
}
