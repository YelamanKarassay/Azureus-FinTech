# CLAUDE.md — Azureus Project Conventions for Claude Code

> This file is read by Claude Code at the start of every session. Keep it short, opinionated, and current. When project conventions change, update this file first.

---

## What This Project Is

**Azureus** is an open-source educational research platform for systematic equity strategies on Hong Kong equities. Backtester + showcase strategies + interactive visualization. Deployed at `azureus.tech`. MIT licensed.

For full context, read `docs/ARCHITECTURE.md`. **You should reference it before making any structural decision.**

---

## How to Work in This Repo

### Read these files first, in this order:
1. This file (`CLAUDE.md`) — conventions and rules
2. `docs/ARCHITECTURE.md` — full architectural decisions and rationale
3. The relevant section's locked block in ARCHITECTURE.md before changing that section's code
4. The current phase's success criteria in ARCHITECTURE.md Section 9

### When in doubt, ask. When not in doubt, also consider asking.
This project is being built with deliberate trade-offs. Defaults from web tutorials are often wrong for this codebase. If you're tempted to suggest something not in ARCHITECTURE.md, treat that as a signal to confirm with the developer before writing code.

---

## Stack (Locked — Do Not Substitute)

| Layer | Choice | Don't suggest |
|---|---|---|
| Backend language | Python 3.11+ | Java, Go, Rust |
| Web framework | FastAPI | Flask, Django, Litestar |
| Data validation | Pydantic v2 | dataclasses-only, marshmallow |
| DataFrame validation | Pandera | Great Expectations, hand-rolled |
| ORM / DB access | SQLAlchemy 2.x | Django ORM, raw SQL only |
| Migrations | Alembic | (none) |
| Database | Postgres 16 + TimescaleDB | MongoDB, MySQL, Cassandra, DuckDB |
| Cache + queue | Redis 7 | Memcached, RabbitMQ |
| Job queue | RQ (Redis Queue) | Celery, Arq, Dramatiq |
| Orchestration | Prefect 3 | Airflow, Dagster, cron |
| ML framework | LightGBM, scikit-learn, numpy, pandas | XGBoost, CatBoost (for primary GBM) |
| Experiment tracking | MLflow | Weights & Biases, Comet, Neptune |
| Linter / formatter | ruff | black, flake8, isort, pylint |
| Type checker | mypy | pyright (CI only — local fine) |
| Frontend build | Vite | Next.js, Create React App, Remix |
| Frontend lib | React 18+ | Vue, Svelte, Solid |
| Router | TanStack Router | React Router, Wouter |
| Server state | TanStack Query | SWR, Redux Toolkit Query |
| UI state | Zustand | Redux, Jotai, Recoil |
| Component lib | shadcn/ui + Tailwind | Material UI, Chakra, Ant Design |
| Charts | Plotly.js (via react-plotly.js) | Recharts, Chart.js, D3, visx |
| Container runtime | Docker + Docker Compose | k8s, Swarm, Nomad |
| TLS / reverse proxy | Caddy | nginx, Traefik, HAProxy |
| Deployment | Azure VM (single) | AWS, GCP, multi-region |
| CI/CD | GitHub Actions | CircleCI, GitLab CI, Jenkins |
| Container registry | GitHub Container Registry | Docker Hub, ECR |

If a task requires a tool not on this list, stop and ask before installing it.

---

## Hard Rules — Violating These Breaks the Project

### Rule 1: PIT (Point-In-Time) Correctness Is Non-Negotiable

Every fundamental record stores both `period_end` (fiscal date) and `reported_date` (announcement date). Every macro record stores both `date` (value-date) and `reported_date`. Strategy code never queries raw tables — only through `DataSource` methods that take `as_of_date` and filter `reported_date <= as_of_date`.

If you write code that uses fundamentals data indexed only by period_end without filtering by reported_date, you've created lookahead bias. This is a critical correctness bug in this domain.

### Rule 2: Strategies Are Provider-Agnostic

Strategy code touches `DataSource` (the interface), never `BloombergDataSource` or `YFinanceDataSource` directly. The same strategy code must work with either implementation. If you find yourself importing a specific provider in strategy code, stop and refactor.

### Rule 3: The Strategy Interface Is Stable

The `Strategy` ABC contract (`rebalance_dates`, `target_weights`, `fit`, params via Pydantic) is locked. Adding new strategies = implementing this interface. Modifying the interface itself requires explicit architectural change discussion, not a code change.

### Rule 4: All Backtest Execution Goes Through the Job Queue

Even fast backtests. No sync HTTP endpoint that runs a backtest inline. Reason: uniform programming model, async-everywhere matches production patterns, prevents accidental long-blocking endpoints.

### Rule 5: Reproducibility Fields Are Mandatory on Job Records

Every `jobs` row records: `code_version` (git SHA), `dependencies_lock` (pip-freeze), `git_status_clean` (bool), `as_of_timestamp`, explicit random seeds in `params`. Don't write code paths that create jobs without these fields populated.

### Rule 6: Don't Add Containers Without Discussion

Container count is 7 in production. Adding an 8th container is an architectural decision, not an implementation choice. Tools that don't justify their own container should run as Python libraries inside an existing container.

### Rule 7: Bloomberg Data Is Never in the Public Repo

Bloomberg-sourced data files, extracted Excel files, exported CSVs from BBG — none of these go in git. The `.gitignore` enforces this. If you're staging Bloomberg-derived data for commit, stop.

### Rule 8: No User Accounts in v1 or v2

The project is open-access by design. Don't introduce auth tables, user models, JWT, OAuth, or session management. Admin endpoints get HTTP Basic Auth at Caddy, single shared credential. Rate-limiting is per-IP via slowapi.

---

## File Layout (Authoritative)

```
azureus/                         # Python package root
  data/
    sources/                     # DataSource implementations
    schemas.py                   # Pydantic models for internal data
    db.py                        # SQLAlchemy session, query helpers
  features/
    base.py                      # Feature Protocol
    fundamentals/                # value, quality features
    market/                      # momentum, low_vol features
    macro/                       # (Phase 2)
    registry.py                  # central feature catalog
  models/
    base.py
    gbm.py                       # LightGBM wrapper
    cv/
      purged_kfold.py
      walk_forward.py
  strategies/
    base.py                      # Strategy ABC, StrategyParams, StrategyContext
    multi_factor_v1.py
    gbm_factors_v1.py
    benchmark.py
    registry.py
    docs/                        # methodology markdown per strategy
  backtesting/
    engine.py
    portfolio.py
    cost_model.py
    metrics.py
    results.py
  api/
    main.py                      # FastAPI app
    routes/
    schemas.py                   # Request/response Pydantic models
    rate_limit.py
  worker/
    tasks.py                     # RQ task definitions
  pipelines/                     # Prefect flows
    ingest_prices_free.py
    ingest_prices_bbg.py
    ...
  utils/
    dates.py                     # trading calendars, business days
    universe.py
    reproducibility.py           # git SHA capture, pip freeze

frontend/                        # Vite + React app
  src/
    components/
      ui/                        # shadcn primitives
      charts/                    # 8 Plotly chart components
      layout/
      strategy/
      backtest/
    pages/
    hooks/
    api/
    stores/                      # Zustand
    types/
    utils/

services/                        # per-service Dockerfiles + configs
  api/Dockerfile
  worker/Dockerfile
  base/Dockerfile                # shared Python base image
  caddy/Caddyfile
  postgres/                      # TimescaleDB image config
  prefect/
  mlflow/

alembic/                         # database migrations
  versions/
  env.py

docs/
  ARCHITECTURE.md                # the planning document
  RUNBOOK.md                     # operational procedures
  disaster-recovery.md

scripts/                         # one-off operational scripts
.github/workflows/               # CI/CD
docker-compose.yml
docker-compose.override.yml      # local-only overrides
docker-compose.prod.yml          # production overrides
pyproject.toml
.env.example
CLAUDE.md                        # this file
README.md
```

When creating new files, place them in the right directory. When you can't tell where something belongs, ask.

---

## Coding Standards

### Python

- **Type hints on every function signature.** No exceptions for "trivial" functions.
- **Pydantic for data shapes that cross module boundaries.** Plain dataclasses or attrs are fine for internal-only.
- **`from __future__ import annotations` at the top of every file.** Forward references everywhere.
- **Docstrings:** Google style. Required on all public functions, classes, modules.
- **No `print()` for logging.** Use `logging` module with the project's logger config.
- **No bare `except:`.** Specify exception types.
- **No `# type: ignore` without a comment explaining why.**
- **Async functions only where async actually matters** (HTTP handlers, DB calls, Redis calls). Don't make compute-bound code async.

### TypeScript

- **Strict mode on.** `"strict": true` in tsconfig.
- **No `any`.** If you genuinely need it, use `unknown` and narrow, or write a justifying comment.
- **Component props typed.** No implicit any on props.
- **No barrel files (`index.ts` re-exports).** Direct imports. Easier to grep, no circular import surprises.
- **`React.FC` is not required.** Just type props directly.

### SQL

- **No queries in route handlers.** Route → service function → query function. Three layers minimum.
- **Parameterized queries always.** SQLAlchemy makes this automatic; if you write raw SQL, never string-format values in.
- **EXPLAIN ANALYZE any new query that touches a hot path** (backtest data loading, PIT fundamentals lookup).

---

## Testing Standards

### Required tests (don't merge without):
- **PIT correctness test** — every change to fundamentals query path must pass the `AuditingDataSource` lookahead regression test
- **Migration tests** — every Alembic migration must apply cleanly from empty schema and from previous version
- **Cost model unit tests** — any change to fees must include a test asserting expected bps on a known trade
- **Strategy regression tests** — Strategy 1 and Strategy 2 each have a "golden output" test that asserts a known backtest produces the same Sharpe / drawdown within tolerance

### Skip these (intentionally low value):
- Trivial component render tests
- 100% coverage padding tests
- Tests that just assert constructors don't crash

### Coverage targets:
- Core logic (backtester, features, cost model, CV): 90%
- API routes: path coverage on happy + error paths
- Frontend: ~50%, focused on logic-rich components

---

## Common Mistakes to Avoid

These are things web tutorials get wrong for this domain. Don't propagate them.

1. **Naive k-fold CV on time series.** We use *purged k-fold with embargo*, expanding-window walk-forward. Not random shuffle.

2. **Sharpe from monthly returns.** We compute Sharpe from *daily* returns annualized. Monthly understates volatility.

3. **Max drawdown as peak-to-trough.** Wrong. We measure peak-to-recovery for duration.

4. **Imputing missing fundamentals.** v1 *excludes* tickers missing required features. No imputation. Documented as a methodological choice.

5. **Using `provider` as a default parameter.** Always required. Code that assumes a default provider is a bug waiting to happen.

6. **Polling at sub-second intervals.** 2 seconds. Faster doesn't help users and burns API resources.

7. **Storing prices as FLOAT.** NUMERIC(18, 6) always. Floats accumulate error.

8. **Using `datetime.now()` in production code paths.** Use injectable clock for testability. `datetime.now()` outside of logging is a code smell.

9. **Catching exceptions and continuing silently in ingestion.** Failures get logged to `ingestion_runs` with full context. No silent swallows.

10. **Treating Bloomberg as a live data source.** It's bulk extraction → Postgres. `DataSource` reads from our DB, never from Bloomberg APIs directly.

---

## When You're About to Suggest Something New

Pause and check:

- Is it in `docs/ARCHITECTURE.md`? If no, ask before proceeding.
- Does it conflict with a "Hard Rule" above? If yes, stop.
- Would it add a container? If yes, ask.
- Would it require user accounts or auth beyond admin Basic Auth? If yes, stop.
- Would it require a new third-party service? If yes, ask.
- Is it on the "Don't suggest" column of the Stack table? If yes, stop.

---

## Current Phase

> **Update this section as phases progress.**

**Current phase:** Phase 0 (local foundation complete; production deploy deferred) → starting Phase 1 — Data Layer

**Phase 0 status (as of 2026-05-12):** Local foundation done — public GitHub repo, two-job CI both green, local Docker Compose for Postgres+TimescaleDB and Redis (verified healthy), FastAPI `/api/v1/health` and `/api/v1/version`, Vite+React+TanStack Query frontend reading the health endpoint via Vite proxy. **Production deployment is deferred:** Azure for Students region policy blocked VM provisioning in every region attempted. Decision (developer): pause deploy work, continue local development, re-evaluate cloud provider (likely return to DigitalOcean or pick a region-permissive alternative) before sealing Phase 0.

**Phase 0 open items (must close before `v0.1.0-foundation` tag):** cloud provider final selection, VM provisioning, get.tech DNS A-records, Caddy + TLS + `docker-compose.prod.yml`, `services/base/Dockerfile` + `services/api/Dockerfile`, `.github/workflows/deploy.yml`, UptimeRobot monitor, screenshots.

**Phase 0 success criterion (unchanged):** A stranger visiting `azureus.tech` sees a working React page reading a live `/api/v1/health`. TLS valid. CI badge green. Push-to-main auto-deploys in <8 min.

**Phase 1 entry condition:** continuing into Phase 1 is an *explicit deferral*, not silent drift. The deployment items above reopen as soon as a host is selected; track them as carryover, do not let them quietly disappear.

---

## Communication With the Developer

- The developer is doing this as both a portfolio piece and a learning exercise. Explain *why*, not just *how*, when relevant.
- The developer prefers direct technical feedback. If something is wrong, say so plainly.
- When the developer asks for help on a stuck problem, follow the 2-Day Rule from the architecture doc: ask whether the problem is a scope issue, an approach issue, or a knowledge gap. Different responses for each.
- Don't over-explain basics the developer already knows (advanced Python, React, SQL). Do explain things specific to this domain (PIT, purged CV, factor regression methodology).

---

**End of CLAUDE.md. Last updated: project planning lock (v1.0).**
