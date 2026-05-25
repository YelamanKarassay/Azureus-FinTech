import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiFetch } from './client'
import type {
  BacktestCreateRequest,
  BacktestCreateResponse,
  BacktestResultResponse,
  BacktestStatusResponse,
} from '../types/api'

const TERMINAL_STATUSES = new Set(['completed', 'failed'])

export function useCreateBacktest() {
  const queryClient = useQueryClient()
  return useMutation<BacktestCreateResponse, Error, BacktestCreateRequest>({
    mutationFn: (payload) =>
      apiFetch<BacktestCreateResponse>('/backtests', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['backtests'] })
    },
  })
}

export function useBacktests() {
  return useQuery<BacktestStatusResponse[]>({
    queryKey: ['backtests'],
    queryFn: () => apiFetch<BacktestStatusResponse[]>('/backtests'),
    refetchInterval: 10_000,
  })
}

export function useBacktestStatus(jobId: string | undefined) {
  return useQuery<BacktestStatusResponse>({
    queryKey: ['backtest', jobId, 'status'],
    queryFn: () => apiFetch<BacktestStatusResponse>(`/backtests/${jobId}`),
    enabled: Boolean(jobId),
    refetchInterval: (query) => {
      const status = query.state.data?.status
      return status && TERMINAL_STATUSES.has(status) ? false : 2_000
    },
  })
}

export function useBacktestResult(
  jobId: string | undefined,
  enabled: boolean,
) {
  return useQuery<BacktestResultResponse>({
    queryKey: ['backtest', jobId, 'result'],
    queryFn: () =>
      apiFetch<BacktestResultResponse>(`/backtests/${jobId}/result`),
    enabled: Boolean(jobId) && enabled,
  })
}
