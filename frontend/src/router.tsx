import {
  RouterProvider,
  createRootRoute,
  createRoute,
  createRouter,
} from '@tanstack/react-router'
import { AppShell } from './components/layout/AppShell'
import { BacktestResultPage } from './pages/BacktestResultPage'
import { StrategyDetailPage } from './pages/StrategyDetailPage'
import { StrategyGalleryPage } from './pages/StrategyGalleryPage'

const rootRoute = createRootRoute({
  component: AppShell,
})

const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/',
  component: StrategyGalleryPage,
})

const strategyRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/strategies/$strategyId',
  component: StrategyDetailPage,
})

const backtestRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/backtests/$jobId',
  component: BacktestResultPage,
})

const routeTree = rootRoute.addChildren([
  indexRoute,
  strategyRoute,
  backtestRoute,
])

const router = createRouter({ routeTree })

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router
  }
}

export function AppRouter() {
  return <RouterProvider router={router} />
}
