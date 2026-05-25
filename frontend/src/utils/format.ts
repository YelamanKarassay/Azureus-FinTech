export function formatCurrency(value: number | string | null | undefined) {
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return '—'
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'HKD',
    maximumFractionDigits: 0,
  }).format(numeric)
}

export function formatNumber(value: number | string | null | undefined) {
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return '—'
  return new Intl.NumberFormat('en-US', {
    maximumFractionDigits: 2,
  }).format(numeric)
}

export function formatPercent(value: number | string | null | undefined) {
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return '—'
  return `${(numeric * 100).toFixed(2)}%`
}

export function formatDate(value: string | null | undefined) {
  if (!value) return '—'
  return value.slice(0, 10)
}
