import { Plot } from './Plot'
import type { BacktestResultResponse } from '../../types/api'
import {
  drawdownSeries,
  holdingsCountSeries,
  latestHoldings,
  rollingSeries,
} from '../../utils/analytics'
import { formatCurrency, formatNumber, formatPercent } from '../../utils/format'

const PLOT_CONFIG = {
  displayModeBar: false,
  responsive: true,
}

const PLOT_LAYOUT = {
  autosize: true,
  margin: { t: 24, r: 20, b: 36, l: 56 },
  paper_bgcolor: 'rgba(0,0,0,0)',
  plot_bgcolor: 'rgba(0,0,0,0)',
  font: { color: '#3f3f46', family: 'Inter, system-ui, sans-serif' },
  xaxis: { gridcolor: '#e4e4e7' },
  yaxis: { gridcolor: '#e4e4e7' },
}

export function ResultDashboard({ result }: { result: BacktestResultResponse }) {
  const equity = result.equity_curve
  const drawdowns = drawdownSeries(equity)
  const rolling = rollingSeries(equity)
  const holdingsCount =
    result.holdings.length > 0
      ? holdingsCountSeries(result.holdings)
      : equity.map((row) => ({ date: row.date, count: 0 }))
  const holdings = latestHoldings(result.holdings)
  const totalCost = result.trades.reduce(
    (sum, trade) => sum + (trade.total_cost ?? 0),
    0,
  )
  const equityValues = equity.map((row) => row.total_value)
  const drawdownValues = drawdowns.map((row) => row.drawdown)
  const rollingVolValues = rolling
    .map((row) => row.rollingVol)
    .filter((value): value is number => value !== null)
  const rollingSharpeValues = rolling
    .map((row) => row.rollingSharpe)
    .filter((value): value is number => value !== null)
  const holdingsCountValues = holdingsCount.map((row) => row.count)
  const icSeries = diagnosticsArray(result.diagnostics?.ic_series)
  const mlflowRunIds = diagnosticsRunIds(result.diagnostics?.mlflow_run_ids)

  return (
    <div className="space-y-6">
      <section className="grid gap-3 md:grid-cols-4">
        <Metric label="Final value" value={formatCurrency(result.summary.final_value)} />
        <Metric label="Total return" value={formatPercent(result.summary.total_return)} />
        <Metric label="Sharpe" value={formatNumber(result.summary.sharpe)} />
        <Metric label="Max drawdown" value={formatPercent(result.summary.max_drawdown)} />
      </section>

      <section className="grid gap-5 xl:grid-cols-2">
        <ChartPanel title="Equity curve">
          <Plot
            className="h-72 w-full"
            data={[
              {
                x: equity.map((row) => row.date),
                y: equity.map((row) => row.total_value),
                type: 'scatter',
                mode: 'lines',
                line: { color: '#0f766e', width: 2 },
                name: 'Total value',
              },
            ]}
            layout={{
              ...PLOT_LAYOUT,
              yaxis: {
                ...PLOT_LAYOUT.yaxis,
                range: paddedRange(equityValues, 0.005),
                separatethousands: true,
                tickformat: ',.0f',
                tickprefix: 'HK$',
              },
            }}
            config={PLOT_CONFIG}
            useResizeHandler
          />
        </ChartPanel>

        <ChartPanel title="Drawdown">
          <Plot
            className="h-72 w-full"
            data={[
              {
                x: drawdowns.map((row) => row.date),
                y: drawdowns.map((row) => row.drawdown),
                type: 'scatter',
                mode: 'lines',
                fill: 'tozeroy',
                line: { color: '#be123c', width: 2 },
                name: 'Drawdown',
              },
            ]}
            layout={{
              ...PLOT_LAYOUT,
              yaxis: {
                ...PLOT_LAYOUT.yaxis,
                range: negativePercentRange(drawdownValues),
                tickformat: '.1%',
              },
            }}
            config={PLOT_CONFIG}
            useResizeHandler
          />
        </ChartPanel>

        <ChartPanel title="Rolling risk">
          <Plot
            className="h-72 w-full"
            data={[
              {
                x: rolling.map((row) => row.date),
                y: rolling.map((row) => row.rollingVol),
                type: 'scatter',
                mode: 'lines',
                line: { color: '#2563eb', width: 2 },
                name: '20-day annualized vol',
                yaxis: 'y',
              },
              {
                x: rolling.map((row) => row.date),
                y: rolling.map((row) => row.rollingSharpe),
                type: 'scatter',
                mode: 'lines',
                line: { color: '#a16207', width: 2 },
                name: '20-day Sharpe',
                yaxis: 'y2',
              },
            ]}
            layout={{
              ...PLOT_LAYOUT,
              yaxis: {
                ...PLOT_LAYOUT.yaxis,
                range: zeroBasedRange(rollingVolValues, 0.05),
                tickformat: '.1%',
              },
              yaxis2: {
                range: paddedRange(rollingSharpeValues, 0.1, [0, 1]),
                overlaying: 'y',
                side: 'right',
                gridcolor: 'rgba(0,0,0,0)',
              },
              legend: { orientation: 'h' },
            }}
            config={PLOT_CONFIG}
            useResizeHandler
          />
        </ChartPanel>

        <ChartPanel title="Holdings count">
          <Plot
            className="h-72 w-full"
            data={[
              {
                x: holdingsCount.map((row) => row.date),
                y: holdingsCount.map((row) => row.count),
                type: 'bar',
                marker: { color: '#52525b' },
                name: 'Holdings',
              },
            ]}
            layout={{
              ...PLOT_LAYOUT,
              yaxis: {
                ...PLOT_LAYOUT.yaxis,
                dtick: 1,
                range: zeroBasedRange(holdingsCountValues, 1),
              },
            }}
            config={PLOT_CONFIG}
            useResizeHandler
          />
        </ChartPanel>
      </section>

      <section className="grid gap-5 xl:grid-cols-2">
        {icSeries.length > 0 && (
          <ChartPanel title="Information coefficient">
            <Plot
              className="h-72 w-full"
              data={[
                {
                  x: icSeries.map((row) => row.date),
                  y: icSeries.map((row) => row.ic),
                  type: 'bar',
                  marker: { color: '#0f766e' },
                  name: 'IC',
                },
              ]}
              layout={{
                ...PLOT_LAYOUT,
                yaxis: {
                  ...PLOT_LAYOUT.yaxis,
                  range: paddedRange(
                    icSeries.map((row) => row.ic),
                    0.15,
                    [-0.2, 0.2],
                  ),
                },
              }}
              config={PLOT_CONFIG}
              useResizeHandler
            />
          </ChartPanel>
        )}

        {mlflowRunIds.length > 0 && (
          <div className="rounded-md border border-zinc-200 bg-white">
            <div className="border-b border-zinc-200 px-4 py-3">
              <h2 className="font-semibold">MLflow runs</h2>
            </div>
            <div className="divide-y divide-zinc-100">
              {mlflowRunIds.map(([windowId, runId]) => (
                <a
                  key={runId}
                  className="block px-4 py-3 text-sm text-teal-700 hover:bg-zinc-50"
                  href={`https://mlflow.azureus.tech/#/experiments/0/runs/${runId}`}
                  target="_blank"
                  rel="noreferrer"
                >
                  <span className="font-mono">{windowId}</span>
                  <span className="ml-3 font-mono text-xs text-zinc-500">{runId}</span>
                </a>
              ))}
            </div>
          </div>
        )}
      </section>

      <section className="grid gap-5 xl:grid-cols-2">
        <div className="rounded-md border border-zinc-200 bg-white">
          <div className="border-b border-zinc-200 px-4 py-3">
            <h2 className="font-semibold">Latest holdings</h2>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="bg-zinc-50 text-xs uppercase text-zinc-500">
                <tr>
                  <th className="px-4 py-3">Ticker</th>
                  <th className="px-4 py-3">Weight</th>
                  <th className="px-4 py-3">Market value</th>
                </tr>
              </thead>
              <tbody>
                {holdings.length === 0 ? (
                  <tr className="border-t border-zinc-100">
                    <td className="px-4 py-4 text-zinc-500" colSpan={3}>
                      No holdings recorded for this result.
                    </td>
                  </tr>
                ) : (
                  holdings.slice(0, 12).map((row) => (
                    <tr key={row.ticker} className="border-t border-zinc-100">
                      <td className="px-4 py-3 font-mono">{row.ticker}</td>
                      <td className="px-4 py-3">{formatPercent(row.weight)}</td>
                      <td className="px-4 py-3">
                        {formatCurrency(row.market_value)}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>

        <div className="rounded-md border border-zinc-200 bg-white">
          <div className="flex items-center justify-between border-b border-zinc-200 px-4 py-3">
            <h2 className="font-semibold">Trades and costs</h2>
            <span className="text-sm text-zinc-500">
              {formatCurrency(totalCost)}
            </span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="bg-zinc-50 text-xs uppercase text-zinc-500">
                <tr>
                  <th className="px-4 py-3">Ticker</th>
                  <th className="px-4 py-3">Shares</th>
                  <th className="px-4 py-3">Cost</th>
                </tr>
              </thead>
              <tbody>
                {result.trades.length === 0 ? (
                  <tr className="border-t border-zinc-100">
                    <td className="px-4 py-4 text-zinc-500" colSpan={3}>
                      No trades recorded for this result.
                    </td>
                  </tr>
                ) : (
                  result.trades.slice(0, 12).map((row, index) => (
                    <tr
                      key={`${row.ticker}-${row.executed_at ?? index}`}
                      className="border-t border-zinc-100"
                    >
                      <td className="px-4 py-3 font-mono">{row.ticker}</td>
                      <td className="px-4 py-3">{formatNumber(row.shares)}</td>
                      <td className="px-4 py-3">
                        {formatCurrency(row.total_cost)}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </section>
    </div>
  )
}

function diagnosticsArray(value: unknown): Array<{ date: string; ic: number }> {
  if (!Array.isArray(value)) return []
  return value
    .map((row) => {
      if (!row || typeof row !== 'object' || Array.isArray(row)) return null
      const date = 'date' in row ? row.date : undefined
      const ic = 'ic' in row ? row.ic : undefined
      return typeof date === 'string' && typeof ic === 'number'
        ? { date, ic }
        : null
    })
    .filter((row): row is { date: string; ic: number } => row !== null)
}

function diagnosticsRunIds(value: unknown): Array<[string, string]> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return []
  return Object.entries(value).filter(
    (entry): entry is [string, string] => typeof entry[1] === 'string',
  )
}

function paddedRange(
  values: number[],
  percentPadding: number,
  fallback: [number, number] = [0, 1],
): [number, number] {
  if (values.length === 0) return fallback
  const min = Math.min(...values)
  const max = Math.max(...values)
  const span = max - min
  const absolutePadding = Math.max(Math.abs(max || min) * percentPadding, 1)
  const padding = span > 0 ? span * percentPadding : absolutePadding
  return [min - padding, max + padding]
}

function zeroBasedRange(
  values: number[],
  fallbackMax: number,
): [number, number] {
  if (values.length === 0) return [0, fallbackMax]
  const max = Math.max(...values)
  return [0, Math.max(max * 1.15, fallbackMax)]
}

function negativePercentRange(values: number[]): [number, number] {
  if (values.length === 0) return [-0.05, 0.01]
  const min = Math.min(...values)
  return [Math.min(min * 1.15, -0.05), 0.01]
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-zinc-200 bg-white px-4 py-3">
      <p className="text-xs font-medium uppercase text-zinc-500">{label}</p>
      <p className="mt-2 text-xl font-semibold text-zinc-950">{value}</p>
    </div>
  )
}

function ChartPanel({
  title,
  children,
}: {
  title: string
  children: React.ReactNode
}) {
  return (
    <div className="rounded-md border border-zinc-200 bg-white">
      <div className="border-b border-zinc-200 px-4 py-3">
        <h2 className="font-semibold">{title}</h2>
      </div>
      <div className="p-2">{children}</div>
    </div>
  )
}
