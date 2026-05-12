# Azureus

> Open-source educational research platform for systematic equity strategies on Hong Kong equities.

**Status:** WIP — in active development (Phase 0 of 5).

- Live site: [azureus.tech](https://azureus.tech) *(deployment pending Phase 0 completion)*
- Architecture: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- Conventions for contributors / Claude Code: [`CLAUDE.md`](CLAUDE.md)
- License: MIT

## What this is

A pedagogical research tool for finance/FinTech students learning systematic strategies. Three showcase strategies (market-cap benchmark, multi-factor cross-sectional, LightGBM on factor features) backtested with rigorous methodology (point-in-time fundamentals, purged k-fold cross-validation, HK-specific transaction costs) and presented with rich, interactive visualizations.

## What this is *not*

Not a trading system, not a real-time platform, not a code-execution platform, not competing with vectorbt/Backtrader/QuantConnect. See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) Appendix B for the full non-goals list.

## Quickstart (local dev)

```bash
# 1. Install dependencies (uv >= 0.4.27)
uv sync

# 2. Start Postgres + Redis
cp .env.example .env
docker compose up -d

# 3. Run the API
uv run uvicorn azureus.api.main:app --reload
```

API will be at `http://localhost:8000`. OpenAPI docs at `http://localhost:8000/api/v1/docs`.

## Stack

Python 3.11+ · FastAPI · SQLAlchemy 2.x · Postgres 16 + TimescaleDB · Redis 7 · RQ · Prefect 3 · LightGBM · MLflow · Vite + React 18 · TanStack Router/Query · shadcn/ui + Tailwind · Plotly.js · Docker Compose · Caddy · DigitalOcean.

Full stack table and rationale in [`CLAUDE.md`](CLAUDE.md) and [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).
