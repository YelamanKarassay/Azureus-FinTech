# Phase 3 Checklist — Strategy 1 + API + Frontend (Days 23–34)

> **Goal (per ARCHITECTURE §9.2):** Strategy 1 runs end-to-end through the
> frontend → FastAPI → RQ worker → Postgres result path. Phase 3 was first
> verified locally, then deployed to the Azure VM after the Phase 0 hosting
> blocker was resolved.

---

## Locked Phase 3 Decisions

- **Exit target:** local end-to-end flow, not `azureus.tech`.
- **Data path:** yfinance demo PIT fundamentals first; Webull is optional and
  non-blocking; Bloomberg remains the research-grade Phase 5 path.
- **Free fundamentals limitation:** yfinance HK fundamentals are sparse and
  recent. Strategy 1 demo may use a shorter covered window; no synthetic
  fundamentals for public showcase unless explicitly documented.
- **Execution:** all backtests still go through RQ. No sync backtest endpoint.
- **Frontend:** vertical slices; build one working Strategy 1 path before
  broad UI polish.

---

## Day 23 — Feature Interface + Market Features

- [x] `azureus/features/base.py` — locked `Feature` Protocol
- [x] `azureus/features/registry.py` — central feature catalog
- [x] `azureus/features/market/price.py`:
  - `momentum_12_1`
  - `realized_vol_252d` (sign-flipped)
  - `beta_252d` (sign-flipped, equal-weight universe proxy)
- [x] Tests for registry and market feature math

---

## Days 24–25 — Demo PIT Fundamentals

- [x] Implement yfinance financial-statement extraction into normalized
  `fundamentals_pit` rows
- [x] Conservative demo PIT lag: `reported_date = period_end + 90 days`
- [x] Implement `YFinanceDataSource.get_fundamentals(...)`
- [x] Implement `YFinanceDataSource.get_fundamentals_history(...)`
- [x] Tests prove PIT filtering and no future `reported_date` leakage
- [x] Document sparse free-source limitations

---

## Days 26–27 — Fundamental Features + Composite Scoring

- [x] Value features: earnings yield, book-to-price, sales-to-price,
  free-cash-flow-to-price
- [x] Quality features: ROE, gross profitability, debt-to-equity
  sign-flipped, accruals sign-flipped
- [x] Feature-availability filter: no imputation
- [x] Cross-sectional rank → sector z-score helper
- [x] Family score and composite score helpers

---

## Days 28–29 — Strategy 1

- [x] `azureus/strategies/multi_factor_v1.py`
- [x] Params: universe, rebalance frequency, `n_long`, sector-neutral flag,
  factor weights, weighting scheme, liquidity threshold
- [x] Long-only target weights through `DataSource` only
- [x] Tests for liquidity, missing features, sector-neutral ranking, and
  deterministic target weights
- [x] Register Strategy 1

---

## Days 30–31 — API + Worker

- [x] Strategy and feature introspection endpoints
- [x] Backtest create/status/result endpoints
- [x] Service/query layer; no SQL in route handlers
- [x] RQ job creation and worker task
- [x] Jobs include mandatory reproducibility fields
- [x] Persist `BacktestResult.as_dict()` into `backtest_results`
- [x] API and worker tests for success/failure paths

---

## Days 32–34 — Frontend Local E2E

- [x] Routes: strategy gallery/detail and backtest result view
- [x] Strategy 1 params form driven by backend schema
- [x] TanStack Query polling every 2 seconds until terminal job status
- [x] Result charts/tables: summary metrics, equity curve, drawdown,
  rolling metrics, holdings, trades/costs
- [x] Browser verification of the local E2E flow

---

## Phase 3 Exit Criterion

User can locally run Strategy 1 from the frontend, watch the async job
complete, and view persisted results without touching Python scripts.

## Production Addendum

- [x] Azure VM `quantphemes-azure` selected and provisioned
- [x] Production Docker Compose stack runs Caddy, FastAPI, RQ worker,
  Postgres/TimescaleDB, and Redis
- [x] `azureus.tech` and `www.azureus.tech` point to the Azure VM
- [x] Caddy automatic HTTPS certificate issuance verified
- [x] Public API health and production frontend result rendering verified
