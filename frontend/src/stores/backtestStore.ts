import { create } from 'zustand'

interface BacktestStore {
  latestJobId: string | null
  setLatestJobId: (jobId: string) => void
}

export const useBacktestStore = create<BacktestStore>((set) => ({
  latestJobId: null,
  setLatestJobId: (jobId) => set({ latestJobId: jobId }),
}))
