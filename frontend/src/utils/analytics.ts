import type { EquityCurveRow, HoldingRow } from '../types/api'

export interface DrawdownPoint {
  date: string
  drawdown: number
}

export interface RollingPoint {
  date: string
  rollingVol: number | null
  rollingSharpe: number | null
}

export interface HoldingsCountPoint {
  date: string
  count: number
}

export function drawdownSeries(rows: EquityCurveRow[]): DrawdownPoint[] {
  let peak = 0
  return rows.map((row) => {
    peak = Math.max(peak, row.total_value)
    return {
      date: row.date,
      drawdown: peak > 0 ? row.total_value / peak - 1 : 0,
    }
  })
}

export function rollingSeries(
  rows: EquityCurveRow[],
  windowSize = 20,
): RollingPoint[] {
  return rows.map((row, index) => {
    const window = rows
      .slice(Math.max(0, index - windowSize + 1), index + 1)
      .map((item) => item.daily_return ?? 0)
    if (window.length < Math.min(windowSize, rows.length)) {
      return {
        date: row.date,
        rollingVol: null,
        rollingSharpe: null,
      }
    }
    const mean =
      window.reduce((sum, value) => sum + value, 0) / Math.max(window.length, 1)
    const variance =
      window.reduce((sum, value) => sum + (value - mean) ** 2, 0) /
      Math.max(window.length - 1, 1)
    const dailyVol = Math.sqrt(variance)
    const annualVol = dailyVol * Math.sqrt(252)
    return {
      date: row.date,
      rollingVol: annualVol,
      rollingSharpe: annualVol > 0 ? (mean * 252) / annualVol : null,
    }
  })
}

export function holdingsCountSeries(rows: HoldingRow[]): HoldingsCountPoint[] {
  const byDate = new Map<string, Set<string>>()
  rows.forEach((row) => {
    const existing = byDate.get(row.date) ?? new Set<string>()
    existing.add(row.ticker)
    byDate.set(row.date, existing)
  })
  return Array.from(byDate.entries())
    .map(([date, tickers]) => ({ date, count: tickers.size }))
    .sort((a, b) => a.date.localeCompare(b.date))
}

export function latestHoldings(rows: HoldingRow[]) {
  if (rows.length === 0) return []
  const latestDate = rows.reduce((latest, row) =>
    row.date > latest ? row.date : latest,
  rows[0].date)
  return rows
    .filter((row) => row.date === latestDate)
    .sort((a, b) => b.weight - a.weight)
}
