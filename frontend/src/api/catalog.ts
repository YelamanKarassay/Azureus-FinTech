import { useQuery } from '@tanstack/react-query'
import { apiFetch } from './client'
import type {
  FeatureSummary,
  StrategyDetail,
  StrategySummary,
} from '../types/api'

export function useStrategies() {
  return useQuery<StrategySummary[]>({
    queryKey: ['strategies'],
    queryFn: () => apiFetch<StrategySummary[]>('/strategies'),
  })
}

export function useStrategy(strategyId: string) {
  return useQuery<StrategyDetail>({
    queryKey: ['strategy', strategyId],
    queryFn: () => apiFetch<StrategyDetail>(`/strategies/${strategyId}`),
  })
}

export function useFeatures() {
  return useQuery<FeatureSummary[]>({
    queryKey: ['features'],
    queryFn: () => apiFetch<FeatureSummary[]>('/features'),
  })
}
