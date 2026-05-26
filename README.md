# Azureus

Open-source educational research platform for systematic equity strategies on Hong Kong equities.

**Status:** Phase 4 implementation is underway. Azureus is deployed with HTTPS at [azureus.tech](https://azureus.tech); the Phase 4 branch adds Strategy 2, Webull-backed public prices, purged CV, LightGBM, diagnostics, and MLflow.

- Live app: [https://azureus.tech](https://azureus.tech)
- API docs: [https://azureus.tech/api/v1/docs](https://azureus.tech/api/v1/docs)
- Architecture: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- Contributor/Codex conventions: [AGENTS.md](AGENTS.md)
- Claude Code conventions: [CLAUDE.md](CLAUDE.md)
- License: MIT

## What This Is

Azureus is a portfolio and learning project for rigorous quant research workflows:

- Hong Kong equity backtesting with HKEX trading-calendar handling
- Point-in-time data access through a provider-agnostic `DataSource` interface
- Strategy 0: equal-weight HSI benchmark
- Strategy 1: multi-factor cross-sectional long-only strategy
- Strategy 2: LightGBM factor strategy with purged CV and walk-forward training
- Async backtest execution through FastAPI, Redis Queue, and Postgres
- Persisted backtest results with equity curves, holdings, trades, costs, and summary metrics
- React/TanStack frontend for running strategy backtests and reviewing results

The public deployment uses free public data. `public_free` combines Webull historical prices (`provider='webull'`) with yfinance annual/quarterly fundamentals (`provider='yfinance'`) using a conservative PIT reporting lag. Bloomberg-derived data is intentionally excluded from the public repo and deployment.

## What This Is Not

Azureus is not a trading system, broker integration, live signal service, or investment recommendation engine. It is built for education, research workflow demonstration, and portfolio review.

## Current Phase

Phase 3 delivered the first complete vertical slice:

- Feature registry and market/fundamental factors
- Demo PIT fundamentals path with conservative reporting-date lag
- Multi-factor Strategy 1
- Backtest create/status/result API
- RQ worker execution
- Persisted `backtest_results`
- Frontend strategy gallery, parameter form, polling, and result dashboard
- Production deployment on an Azure VM behind Caddy with automatic HTTPS

Phase 4 adds the ML strategy path:

- Webull daily price ingestion from `2018-01-01` where available
- Annual plus quarterly yfinance fundamentals with 90-day `reported_date` lag
- Hybrid `public_free` data provider for public Strategy 2 jobs
- `gbm_factors_v1` with 21-trading-day sector-neutral labels
- Expanding walk-forward LightGBM training with purged k-fold CV
- Result diagnostics: IC series, IC summary stats, feature importance, and MLflow run IDs
- Read-only `/api/v1/ml/runs` endpoints
- Frontend generic JSON-schema params, IC chart, and MLflow links
- Compose/Caddy wiring for protected `https://mlflow.azureus.tech`

## Local Development

Prerequisites:

- Python 3.11+
- `uv`
- Docker + Docker Compose
- Node.js 22+
- `pnpm`

Start the backend dependencies:

```bash
cp .env.example .env
docker compose up -d
```

Install Python dependencies and apply migrations:

```bash
uv sync
uv run alembic upgrade head
```

Run the API:

```bash
uv run uvicorn azureus.api.main:app --reload
```

Run the worker in a second terminal:

```bash
uv run rq worker backtests --url redis://localhost:6379/0
```

Run the frontend in a third terminal:

```bash
cd frontend
pnpm install
pnpm dev
```

Local URLs:

- Frontend: `http://localhost:5173`
- API: `http://localhost:8000`
- OpenAPI: `http://localhost:8000/api/v1/docs`
- Health: `http://localhost:8000/api/v1/health`
- MLflow: `http://localhost:5000`

## Useful Commands

Run quality checks:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy azureus
uv run pytest
```

Run frontend checks:

```bash
cd frontend
pnpm lint
pnpm build
```

Run the benchmark backtest CLI:

```bash
uv run python -m scripts.run_benchmark_backtest \
  --start 2014-01-01 \
  --end 2026-05-22 \
  --initial-capital 1000000
```

Ingest Webull public prices:

```bash
uv run python -m azureus.pipelines.ingest_prices_webull --all-active --start 2018-01-01
```

## Production

Production currently runs on a single Azure VM:

- Caddy serves the Vite build and manages TLS for `azureus.tech`
- FastAPI serves `/api/v1/*`
- Redis powers the RQ backtest queue
- Postgres/TimescaleDB stores market data, jobs, and backtest results
- MLflow tracks Strategy 2 training runs behind Caddy Basic Auth
- The worker executes all backtests asynchronously

Pushes to `main` deploy automatically after the CI workflow passes. The deploy
workflow builds the Vite frontend in GitHub Actions, uploads a release bundle to
the Azure VM, rebuilds the API/worker images on the VM, runs Alembic migrations,
restarts Docker Compose, and smoke-tests `/api/v1/health`.

Required GitHub Actions secrets:

- `AZURE_VM_HOST`
- `AZURE_VM_USER`
- `AZURE_VM_SSH_KEY`
- `AZURE_VM_PORT` optional, defaults to `22`
- `AZURE_VM_APP_DIR` optional, defaults to `/home/azureuser/azureus`

Manual production deploy fallback:

```bash
cd ~/azureus
bash scripts/deploy_production.sh
```

## Methodology Guardrails

The project is built around domain-specific correctness rules:

- Strategies query data only through `DataSource`, never directly through provider implementations.
- Fundamental records include both `period_end` and `reported_date`.
- Strategy code uses `as_of_date` and must not see records with `reported_date > as_of_date`.
- Backtests run through the queue, not synchronously inside HTTP requests.
- Job records capture reproducibility fields such as code version, dependency lock, git cleanliness, timestamp, and explicit seeds.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full project rationale and phase plan.

## Stack

Python 3.11+, FastAPI, Pydantic v2, Pandera, SQLAlchemy 2.x, Alembic, Postgres 16 + TimescaleDB, Redis 7, RQ, Prefect 3, LightGBM, MLflow, Vite, React, TanStack Router, TanStack Query, Zustand, Tailwind/shadcn-style primitives, Plotly.js, Docker Compose, Caddy, GitHub Actions, and GitHub Container Registry.
