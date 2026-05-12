import { useQuery } from '@tanstack/react-query'
import { apiFetch } from './client'

export interface HealthResponse {
  status: string
  version: string
}

export function useHealth() {
  return useQuery<HealthResponse>({
    queryKey: ['health'],
    queryFn: () => apiFetch<HealthResponse>('/health'),
    refetchInterval: 30_000,
  })
}
