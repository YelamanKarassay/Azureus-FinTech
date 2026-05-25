import { Link, Outlet } from '@tanstack/react-router'
import { useHealth } from '../../api/health'

export function AppShell() {
  const { data } = useHealth()

  return (
    <div className="min-h-screen bg-zinc-50 text-zinc-950">
      <header className="border-b border-zinc-200 bg-white">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-5 py-4">
          <div>
            <Link to="/" className="text-xl font-semibold tracking-tight">
              Azureus
            </Link>
            <p className="mt-1 text-sm text-zinc-500">
              Hong Kong equity strategy research
            </p>
          </div>
          <nav className="flex items-center gap-2 text-sm">
            <Link
              to="/"
              className="rounded-md px-3 py-2 text-zinc-700 hover:bg-zinc-100"
              activeProps={{ className: 'bg-zinc-900 text-white hover:bg-zinc-900' }}
            >
              Strategies
            </Link>
            <span className="hidden rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 font-mono text-xs text-emerald-700 sm:inline">
              API {data?.status ?? 'checking'}
            </span>
          </nav>
        </div>
      </header>
      <Outlet />
    </div>
  )
}
