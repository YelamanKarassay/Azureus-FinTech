import { useHealth } from './api/health'

export default function App() {
  const { data, isPending, isError, error } = useHealth()

  return (
    <main className="min-h-screen flex items-center justify-center p-6">
      <div className="max-w-2xl w-full text-center space-y-6">
        <h1 className="text-5xl font-bold tracking-tight text-slate-900">
          Azureus
        </h1>
        <p className="text-lg text-slate-600">
          Open-source educational research platform for systematic equity
          strategies on Hong Kong equities.
        </p>
        <p className="text-sm text-slate-500">
          WIP — in active development. Phase 0 of 5.
        </p>

        <div className="pt-8 border-t border-slate-200">
          <p className="text-xs uppercase tracking-wider text-slate-500 mb-3">
            API status
          </p>
          {isPending && (
            <p className="font-mono text-sm text-slate-400">checking…</p>
          )}
          {isError && (
            <p className="font-mono text-sm text-rose-600">
              unreachable — {error.message}
            </p>
          )}
          {data && (
            <p className="font-mono text-sm text-emerald-600">
              {data.status} · v{data.version}
            </p>
          )}
        </div>
      </div>
    </main>
  )
}
