# Azureus

Open-source educational research platform for systematic equity strategies on Hong Kong equities.

**Status:** Phase 3 complete. Azureus is deployed with HTTPS at [azureus.tech](https://azureus.tech). Phase 4 is next: Strategy 2, purged CV, LightGBM, and MLflow.

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
- Async backtest execution through FastAPI, Redis Queue, and Postgres
- Persisted backtest results with equity curves, holdings, trades, costs, and summary metrics
- React/TanStack frontend for running strategy backtests and reviewing results

The public deployment uses demo-grade free data from yfinance. Bloomberg-derived data is intentionally excluded from the public repo and deployment.

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

Phase 4 will add the ML strategy path: purged k-fold, walk-forward validation, LightGBM, and MLflow tracking.

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

## Production

Production currently runs on a single Azure VM:

- Caddy serves the Vite build and manages TLS for `azureus.tech`
- FastAPI serves `/api/v1/*`
- Redis powers the RQ backtest queue
- Postgres/TimescaleDB stores market data, jobs, and backtest results
- The worker executes all backtests asynchronously

Manual production deploy uses:

```bash
cd ~/azureus
sudo docker compose --env-file .env.prod -f docker-compose.prod.yml up -d
```

Push-to-main auto-deploy is still a Phase 0 carryover item.

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
