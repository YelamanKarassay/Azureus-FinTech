# Azureus — Architecture Document

> **A systematic equity strategy research and educational platform for Hong Kong equities.**
> Open-source, MIT-licensed, deployed at [azureus.tech](https://azureus.tech).

This document is the authoritative architecture reference for the Azureus project. It records what was decided, why it was decided that way, what was considered and rejected, and which decisions are hard to reverse. Read it before making structural changes.

**Document version:** 1.0 (initial planning lock)
**Status:** All 9 sections locked; pre-implementation
**Audience:** developer (current and future), contributors, technically deep reviewers

---

## Table of Contents

1. [Domain & Product](#1-domain--product)
2. [System Architecture](#2-system-architecture)
3. [Data Architecture](#3-data-architecture)
4. [ML Platform](#4-ml-platform)
5. [API & Backend Design](#5-api--backend-design)
6. [Frontend](#6-frontend)
7. [DevOps & Infrastructure](#7-devops--infrastructure)
8. [Code Quality, Testing, Documentation](#8-code-quality-testing-documentation)
9. [Build Order & Milestones](#9-build-order--milestones)

Appendix A: [Hard-to-Reverse Decisions (Master List)](#appendix-a-hard-to-reverse-decisions-master-list)
Appendix B: [Explicit Non-Goals](#appendix-b-explicit-non-goals)
Appendix C: [Deferred Decisions](#appendix-c-deferred-decisions)

---

## 1. Domain & Product

### 1.1 Project Identity

- **Codename:** Azureus
- **Domain:** azureus.tech
- **License:** MIT
- **Repository:** Public from day one, monorepo, marked WIP until v1 ships

**One-line description:** An open-source educational research platform for systematic equity strategies, with rigorous backtesting, rich visualization, and a clean architecture designed for extensibility.

### 1.2 Core Problem Statement

Finance and FinTech students learn systematic strategies primarily through textbooks, papers, and toy examples. The gap between *reading about* a strategy (e.g., a multi-factor cross-sectional model) and *seeing how it actually behaves* across regimes, parameters, and cost assumptions is large and underserved. Existing professional tools (vectorbt, Backtrader, QuantConnect) are powerful but have steep learning curves and are oriented toward practitioners, not learners. Azureus is a pedagogical research tool: a small set of well-implemented showcase strategies, presented visually and interactively, with the methodological rigor (PIT data, purged CV, realistic costs) that students rarely see executed correctly.

### 1.3 Inspiration

TensorFlow Playground and similar Google ML educational visualizations: minimalistic, interactive, pedagogically valuable, opinionated about correctness. Azureus aims for the same feel in the systematic equity strategy domain.

### 1.4 Value Proposition

1. **Educational, not aspirational.** Built for students learning systematic strategies, not practitioners chasing alpha.
2. **Methodological honesty by default.** PIT-correct fundamentals, purged k-fold CV, realistic transaction costs (HK-specific in v1), survivorship-bias-free universes.
3. **Rich visualization.** Each strategy has a dedicated page with equity curves, drawdowns, factor exposures, turnover, cost attribution, performance under different regimes.
4. **Interactive parameter exploration.** Users re-run any showcase strategy with their own parameters.
5. **HK-first, but architecturally general.** v1 ships with HK equity strategies (a deliberate differentiator) but the architecture supports any universe in future phases.

### 1.5 Differentiation From Existing Tools

- **vs. vectorbt / Backtrader / Zipline:** Those are libraries for practitioners. Azureus is a deployed web application for learners. Different category — sidesteps the "why not use vectorbt?" trap entirely.
- **vs. QuantConnect:** QuantConnect is a code-first platform for serious users. Azureus is a no-code visualization-first tool for students.
- **vs. textbook chapters and papers:** Static. Azureus is interactive.

### 1.6 User Personas

1. **Primary: Finance / FinTech student** (undergrad or master's) learning systematic strategies.
2. **Secondary: The developer** — uses the platform for personal research and as a portfolio artifact.
3. **Tertiary: Technical interviewers** evaluating the developer's portfolio. Visit azureus.tech, explore for 5–15 minutes, judge the quality of work.

**Explicitly not a target user:** practitioners running real strategies. They have better tools. We are not competing for them.

### 1.7 Asset Universe (v1)

- **Universe:** Hang Seng Index (HSI) constituents, ~80 names. Optional extension to HSCEI (~50 names) if scope permits.
- **Frequency:** Daily bars (OHLCV with corporate-action adjustments).
- **Fundamentals:** Quarterly, point-in-time-correct (reported with realistic disclosure lag).
- **Macro features:** USD/HKD, HIBOR, oil, gold, VIX, US 10Y yield, China-related macro indicators.
- **History:** Minimum 10 years (2014–present).

### 1.8 Data Sourcing Strategy

**Two-source architecture, abstracted behind a common `DataSource` interface:**

- **`BloombergDataSource`** — Research-grade. Used by the developer locally. Pulls from Bloomberg Terminal at the university lab. Never committed to the public repo. Never deployed publicly. Bloomberg license requires this.

- **`YFinanceDataSource`** (and/or **`AkShareDataSource`** for better HK coverage) — Demo-grade. Free, public, used by the deployed instance. Has documented limitations (no PIT fundamentals, possible survivorship bias, occasional missing HK names).

Both implementations expose identical interfaces. Strategies, backtester, and frontend are agnostic to which is in use. Configuration switches between them.

**Why this matters:** The deployed Azureus runs on demo-grade data; the developer's research is conducted on research-grade Bloomberg data. The honest framing of this in documentation is itself a pedagogical signal about data quality in quant research.

### 1.9 MVP Feature Set (v1, ~2 months)

1. Data ingestion pipeline (Bloomberg + free sources, PIT-correct schema)
2. Data abstraction layer (`DataSource` interface, ≥2 implementations)
3. Backtesting engine (vectorized; HK-specific transaction costs; walk-forward and purged k-fold validation; survivorship-bias-free historical universe)
4. Strategy showcase library:
   - **Strategy 0:** Benchmark — HSI market-cap-weighted
   - **Strategy 1:** Multi-factor cross-sectional (value, quality, momentum, low-vol, sector-neutralized)
   - **Strategy 2:** Gradient-boosted variant — same features, learned non-linearly with purged CV
5. Strategy interface (`Strategy` ABC) for extensibility
6. Performance analytics (Sharpe, Sortino, Calmar, drawdowns, factor exposures, turnover, cost attribution, regime-conditional performance)
7. REST API
8. React dashboard (landing, gallery, detail page with three tabs, parameter exploration)
9. Deployment at `azureus.tech` with TLS
10. Documentation (methodology writeups, architecture overview, contribution guide)

### 1.10 Phase 2 (Post-v1)

- Strategy 3: One DL-based signal (architecture chosen later — cross-sectional transformer, simple GNN, or sequence model)
- Strategy 4: One critically-analyzed implementation of a recent paper
- **Composability layer:** Users compose strategies from pre-built primitives (factors, signals, position sizers) via UI/config — *no code execution*
- Universe expansion (HSCEI, mid-caps)
- Walk-forward optimization framework for hyperparameter tuning
- Long-short strategy variants
- Board-lot share rounding

### 1.11 Phase 3 (Aspirational)

- Sandboxed user-supplied strategy code
- Live signal generation
- Multi-market support
- User accounts

### 1.12 Success Metrics ("Done" for v1)

- All 3 Phase 1 strategies (0, 1, 2) backtested over 10+ years with rigorous methodology
- Each strategy has a dedicated detail page with full visualizations and a written methodology section
- Each strategy is re-runnable with user-supplied parameters via the UI
- Data abstraction layer works with both Bloomberg (private) and a free source (public)
- Live deployment at `azureus.tech` with TLS, reachable, demo-grade data
- Public GitHub repo, MIT-licensed, README sufficient for a reviewer to understand the project in 15 minutes
- All methodological choices documented and defended in writing
- Codebase is clean enough that a contributor could add Strategy 3 by implementing the `Strategy` interface in <200 lines

### 1.13 Rationale: Why This Project Shape

The project shape — *educational research platform with showcase strategies and good extensibility* — was deliberately chosen over three alternatives:

1. **Research-heavy ("2-3 deeply-analyzed strategies, no platform"):** rejected because the interview narrative shifts toward pure quant research, which is weaker for the developer's targeted roles (Data Engineer, Data Scientist, Quant Developer). Also, "open-source educational tool" gives long-term resume value as a maintained project.

2. **Generic configurable backtester platform:** rejected because it invites comparison to mature tools (vectorbt, Backtrader, QuantConnect) the project will lose to. The educational/pedagogical positioning sidesteps this entirely.

3. **Code-importing platform (users upload Python strategies):** rejected for v1 and v2 because of sandboxing security (real engineering, real risk), strategy contract design complexity, and the fact that "compose from pre-built primitives" is more pedagogically valuable than "upload code" for the target audience. Deferred to Phase 3.

### 1.14 Constraints

- **Time:** ~2 months for v1 (~250–300 hours estimated). Phase 2 may extend timeline.
- **Budget:** $100 Azure credit + 12-month free B1S Linux VM (Azure for Students), domain owned. Phases 0–3 run on free B1S ($0/month). At Phase 4 (Strategy 2 / LightGBM training) the VM is resized to B2s (~$30/month, 2 vCPU / 4 GB); the $100 credit covers ~3 months post-upgrade. Net first-year out-of-pocket: ~$200, accepted as worth-it for portfolio benefit.
- **Data licensing:** Bloomberg data is research-only. Cannot be redistributed, deployed publicly, or committed to the repo.
- **Solo developer.** Flexible schedule, ~5–6 hrs/day, 6 days/week.

---

## 2. System Architecture

### 2.1 Service Topology

**Modular monolith with separate worker process**, deployed as 7 containers on a single Azure VM:

```
┌─────────────────────────────────────────────────────────────┐
│      Azure VM (B1S free → B2s at Phase 4, 1–2 vCPU)         │
│                                                             │
│  ┌──────────┐                                               │
│  │  caddy   │  TLS, reverse proxy, serves frontend statics  │
│  └────┬─────┘                                               │
│       │                                                     │
│       ├──► api (FastAPI/uvicorn)                            │
│       │     │                                               │
│       │     ▼                                               │
│       │   worker (Python, RQ)                               │
│       │     │                                               │
│       │     ├──► redis (queue + cache)                      │
│       │     └──► postgres + TimescaleDB                     │
│       │                                                     │
│       ├──► prefect (orchestration server)                   │
│       └──► mlflow (experiment tracking)                     │
└─────────────────────────────────────────────────────────────┘
```

**Reasoning:**
- One Python codebase, two process types (api serves HTTP, worker runs jobs). Strategy library, analytics, and data layer are imported by both — no service-to-service contracts.
- Microservices rejected: solo dev + 2 months + service contracts = doesn't ship. The benefits of microservices don't apply to a solo project; the operational tax is real.
- True monolith rejected: incompatible with the async-job pattern (long-running backtests).
- The phrase to internalize: **"Architect like a service-oriented system, deploy like a monolith."** Clean module boundaries with explicit interfaces, but in-process imports rather than network calls.

### 2.2 Async Pattern: Job Queue Everywhere

All backtest execution goes through the job queue, regardless of expected duration. Sub-second backtests pay a small overhead cost (~200–500ms) for a uniform programming model.

**Flow:**
1. Frontend → `POST /api/v1/backtests` with strategy ID and parameters
2. API validates, creates job row in Postgres, enqueues to Redis (RQ), returns `job_id` and 202 Accepted
3. Worker dequeues, runs backtest, writes results, updates job status
4. Frontend polls `GET /api/v1/backtests/{job_id}` every 2s
5. On completion, frontend fetches `GET /api/v1/backtests/{job_id}/result`

**Reasoning:**
- Strategy 2 (GBM with purged CV) will exceed safe sync HTTP limits (typical 30-60s timeouts).
- Phase 2 deep learning is incompatible with sync.
- Async-by-default is the production pattern; demonstrating it correctly is a portfolio asset.
- Hybrid sync/async rejected: doubles code paths for a false simplicity gain.

### 2.3 Backend Framework: FastAPI

**FastAPI** chosen over Flask, Django, and Litestar.

**Why FastAPI for this project:**
- Async-native (matches async-job pattern, plays well with async Redis and Postgres clients)
- Pydantic-based validation: API contract and internal data classes share types
- Auto-generated OpenAPI docs at `/api/v1/docs` — useful as a portfolio artifact (interviewer-browsable)
- Modern Python ergonomics, native type-hinting expectation matches Data Engineer/Quant Dev role conventions

**Trade-offs considered:**
- Flask: more mature, but synchronous by default; would require Marshmallow + apispec + extensions to recreate FastAPI features
- Django: heavyweight for a research tool, ORM-coupled, not async-friendly
- Litestar: more opinionated than FastAPI, but smaller community → riskier under time pressure

### 2.4 Job Queue: Redis + RQ

**Redis + RQ** chosen over Celery and Arq.

**Why RQ:**
- Jobs are plain Python functions; smallest learning curve
- Adequate for our scale (handful of concurrent jobs)
- Redis serves dual purpose as cache (computed features, repeated backtest results)

**Trade-offs considered:**
- Celery: most mature, but notoriously fiddly to configure; overkill for our scale
- Arq: async-native and modern, but smaller community → time-pressure debugging risk
- Postgres-based queue: avoids new infrastructure but less mature tooling

If Phase 2 needs scheduling, add `rq-scheduler` then.

### 2.5 Data Storage: Postgres + TimescaleDB + Redis

**Single Postgres instance with TimescaleDB extension** for all persistent data:
- Time-series tables (prices, fundamentals_pit, macro) — hypertables where appropriate
- Relational tables (strategies, jobs, universe_membership) — standard Postgres
- Backtest results stored as JSONB

**Redis** for ephemeral state only: job queue, optional caching of computed features and recent results.

**Reasoning:**
- Data is small (<10 GB total for v1), strongly relational, schema-stable, requires PIT correctness — textbook SQL case.
- TimescaleDB gives time-series performance while preserving full Postgres feature set (joins across time-series and relational, ACID, mature tooling).
- **NoSQL alternatives evaluated and rejected:**
  - MongoDB: inappropriate for relational data; "flexible schema" pitch irrelevant when schema is stable; joins are slow; would invite "why MongoDB for relational financial data?" interview red flag.
  - Cassandra: designed for billions of rows; our 200K rows of price data don't justify the operational complexity; no joins; ad-hoc queries require per-pattern table design.
  - InfluxDB/QuestDB: optimized for pure time-series, but our data is *joined* time-series + relational, which Postgres+TimescaleDB handles uniquely well.

**The principle:** choose databases based on access patterns, data shape, and scale — not what's trendy. Default to Postgres. Move off Postgres only when a specific access pattern is genuinely poorly served at *our actual scale*.

### 2.6 Job Status Updates: HTTP Polling

**Frontend polls `GET /api/v1/jobs/{job_id}` every 2 seconds** while a backtest is in progress.

**Reasoning:**
- Backtest runtimes (seconds to minutes) tolerate 2-second polling latency
- Tiny user concurrency makes polling overhead negligible
- SSE and WebSockets evaluated and deferred: SSE is a justified Phase 2 upgrade if intra-backtest progress streaming is added; WebSockets are unjustified given no bidirectional needs
- Polling → SSE migration is localized and non-breaking. Reversible decision.

### 2.7 Communication Pattern Summary

| From | To | Protocol | Pattern |
|---|---|---|---|
| Browser | caddy | HTTPS | Standard |
| caddy | frontend (static) | filesystem | Static file serving |
| caddy | api | HTTP | Reverse proxy |
| Frontend | API | HTTPS/JSON | REST, Pydantic-validated |
| Frontend ↔ API (job status) | HTTPS | Polling, 2s interval |
| API | Postgres | TCP | asyncpg |
| API | Redis | TCP | redis-py / RQ enqueue |
| Worker | Redis | TCP | RQ dequeue |
| Worker | Postgres | TCP | psycopg / SQLAlchemy |

### 2.8 Hard-to-Reverse Decisions

1. Async job queue as the universal execution pattern
2. Modular monolith with shared codebase
3. FastAPI as the framework
4. Postgres + TimescaleDB as primary store

---

## 3. Data Architecture

### 3.1 Point-in-Time Correctness

**The single most important concept in this entire document.**

All time-aware data carries both the date the value pertains to (`period_end` for fundamentals, `date` for macro) and the date it became publicly known (`reported_date`). Strategy code never queries raw tables; it queries through `DataSource` methods that take an `as_of_date` parameter and never return data with `reported_date > as_of_date`. The backtester always passes the simulation date as `as_of_date`, making lookahead bias **structurally impossible at the data layer**.

**Why this matters:** Most retail and academic quant projects suffer from lookahead bias because fundamentals are reported with a lag (e.g., a Q4 statement isn't available on Dec 31; it's available ~6–10 weeks later). Naive backtests use the Q4 number on Dec 31, which is using future information. Reported Sharpe ratios are systematically inflated.

**Concrete enforcement:**
- Every fundamental record has both `period_end` and `reported_date`
- Every macro record has both `date` (value-date) and `reported_date`
- Strategy code never touches raw tables; uses `DataSource` methods gated by `as_of_date`
- The backtester always passes `as_of_date = simulation_date`
- A regression test (`AuditingDataSource` wrapper) verifies no lookahead is structurally possible

### 3.2 Survivorship Bias Mitigation

**Second-most-important concept.**

`universe_membership` is a time-varying interval table mapping (index, ticker) to (start_date, end_date). Strategies query historical universe via `DataSource.get_universe(index_id, as_of_date)` rather than using current snapshots.

**Why this matters:** Companies that were in HSI 10 years ago but have since been delisted or removed don't appear in today's index. Backtesting "the HSI" using today's constituents projects survivors back in time, systematically inflating returns. Academic estimates: 1–4% per year in equity strategies.

**Bloomberg-backed deployment includes delisted ticker history.** Free-source deployment documents residual survivorship bias as a known limitation of public data.

### 3.3 Data Sources

| Data type | Bloomberg (research) | Free (deployment) |
|---|---|---|
| Equity prices | BLPAPI/BDH formulas | yfinance / akshare |
| Fundamentals (PIT) | with `ANNOUNCEMENT_DT` | yfinance, estimated lag = period_end + 60 days |
| Macro features | Bloomberg indices | yfinance, FRED |
| Universe (HSI history) | `INDX_MWEIGHT_HIST` quarterly snapshots | Static committed CSV (derived from Bloomberg) |
| Corporate actions | Sidestepped via adjusted close | Same |

Bloomberg ingestion is **human-in-the-loop**, run from the developer's machine after lab visits. Free-source ingestion is **scheduled**, runs daily on the deployed instance.

### 3.4 DataSource Interface

```python
class DataSource(Protocol):
    def get_universe(self, index_id: str, as_of_date: date) -> list[str]: ...
    def get_universe_history(self, index_id: str, start: date, end: date) -> pd.DataFrame: ...
    def get_prices(self, tickers, start, end, fields=("close",)) -> pd.DataFrame: ...
    def get_fundamentals(self, tickers, as_of_date, metrics) -> pd.DataFrame: ...
    def get_fundamentals_history(self, tickers, start, end, metrics) -> pd.DataFrame: ...
    def get_macro(self, series_ids, start, end) -> pd.DataFrame: ...
    def list_available_tickers(self, index_id=None) -> list[str]: ...
    def list_available_metrics(self) -> list[str]: ...
```

**All time-aware methods take `as_of_date`.** Implementations (`BloombergDataSource`, `YFinanceDataSource`) read from our Postgres tables; the provider distinction is recorded as a column. Strategies are provider-agnostic.

### 3.5 Postgres Schema

Provider isolation via a `provider` column on time-series tables (included in primary keys), not separate schemas. Same shape works for all providers.

Tables:
- **Reference:** `tickers`
- **Time-series (TimescaleDB hypertables):** `prices`, `macro_series`, `feature_cache`
- **Time-series (plain Postgres):** `fundamentals_pit` (sparse, ticker-keyed queries)
- **Universe:** `universe_membership` (interval table)
- **Strategy registry:** `strategies`
- **Execution:** `jobs` (with `code_version`, `as_of_timestamp`, `dependencies_lock`, `git_status_clean` for reproducibility)
- **Results:** `backtest_results` (JSONB blobs keyed by job_id)
- **Lineage:** `ingestion_runs`

Fundamentals stored long-format (one row per metric) for schema stability. NUMERIC types for monetary data.

### 3.6 Indexes

Primary indexes serving:
- PIT fundamentals query: composite on `(ticker, metric, reported_date DESC, provider)` with INCLUDE
- Universe membership lookup: `(index_id, start_date, end_date)`
- Job listing and status queries: partial index on active statuses
- Sector lookups for neutralization

### 3.7 Ingestion Pipelines

**Prefect** (self-hosted, open-source server) orchestrates six flows:
- `ingest_universe_membership` (manual, quarterly)
- `ingest_tickers` (weekly)
- `ingest_prices_bbg` (manual, post-lab)
- `ingest_prices_free` (daily, scheduled, deployed)
- `ingest_fundamentals_bbg` (manual, post-lab)
- `ingest_macro` (mixed: Bloomberg manual, free scheduled)

All ingestion is **idempotent** (Postgres `ON CONFLICT DO UPDATE`), **incremental** (lookback overlap for safety), **validated** (Pandera pre-write), **logged** (`ingestion_runs` lineage rows).

**Why Prefect over Airflow/Dagster:** Python-native decorator API, lightweight deployment, modern observability. Airflow rejected as too heavy for one droplet. Dagster rejected for steeper learning curve under time pressure.

### 3.8 Validation

**Pandera schemas** validate every DataFrame before write. Schema-level (types, columns, nullability) plus semantic checks (price positivity, high≥low, reasonable reporting lags, no future dates, no duplicate keys).

A weekly `validate_db_state` flow audits the full DB for invariant violations (gaps in price series, missing expected fundamentals).

### 3.9 Schema Migrations

**Alembic**, autogenerated where possible, hand-edited for TimescaleDB-specific operations. Migrations applied automatically on container startup via entrypoint script. Seed data (default strategies, universe definitions) handled separately via dedicated seed scripts.

### 3.10 Reproducibility

Every backtest job records:
- `code_version` (git SHA at runtime)
- `dependencies_lock` (pip-freeze snapshot)
- `git_status_clean` (bool — dirty working tree flagged)
- `as_of_timestamp` for data state
- Explicit random seeds in params

Universe definitions and strategy parameters are part of `params`/`universe_id`. Re-running a job by ID re-executes against the same code, dependencies, data state, and parameters; results match within floating-point tolerance.

**Interview narrative:** "Every backtest job records the git SHA, a pip-freeze snapshot, the as-of-timestamp for data, the random seed, and the universe definition version. Re-running with the same parameters reproduces results to within floating-point tolerance. A regression test verifies this."

### 3.11 Hard-to-Reverse Decisions

1. PIT modeling with explicit reported_date columns
2. Provider as a column, not a schema
3. Long-format fundamentals
4. TimescaleDB hypertables on prices and macro
5. Prefect for orchestration

---

## 4. ML Platform

### 4.1 Architecture & Layering

Four logical layers, decoupled by interfaces:

```
┌──────────────────────────────────────────┐
│ Strategy Layer                           │
│   strategies.multi_factor_v1             │
│   strategies.gbm_factors_v1              │
└────────────┬─────────────────────────────┘
             │
┌────────────▼─────────────────────────────┐
│ ML/Models Layer                          │
│   models.gbm_trainer, purged_cv          │
└────────────┬─────────────────────────────┘
             │
┌────────────▼─────────────────────────────┐
│ Feature Layer                            │
│   features.fundamentals, features.market │
└────────────┬─────────────────────────────┘
             │
┌────────────▼─────────────────────────────┐
│ Data Layer (Section 3)                   │
└──────────────────────────────────────────┘
```

The **backtesting engine** is orthogonal: it drives strategies through time and simulates execution. Strategies and the engine know nothing about each other's internals beyond the `Strategy` interface.

### 4.2 Feature Engineering

**Feature interface:** `Feature` Protocol with `name`, `description`, `requires_metrics`, `requires_lookback_days`, and `compute(data, tickers, as_of_date) → Series`.

**Phase 1 catalog (10 features, 4 families):**

| Family | Features |
|---|---|
| Value | earnings_yield, book_to_price, sales_to_price, fcf_to_price |
| Quality | roe, gross_profitability, debt_to_equity (sign-flipped), accruals (sign-flipped) |
| Momentum | momentum_12_1 |
| Low Volatility | realized_vol_252d (sign-flipped), beta_252d (sign-flipped) |

**Registry:** central `_FEATURES` dict; features registered via decorator; strategies reference by name; system can introspect available features.

**Feature caching:** Postgres-backed `feature_cache` table (TimescaleDB hypertable), keyed by `(feature_name, ticker, date, data_provider, feature_version)`. Version bump on logic change naturally invalidates the cache.

**No separate feature store** (Tecton, Feast) — overkill at our scale; Postgres cache gives 90% of the value at 5% of the complexity.

**No imputation in v1.** Tickers missing required features are excluded from rebalance. Documented as deliberate methodological choice.

### 4.3 Strategy Interface

```python
class Strategy(ABC):
    id: str
    name: str
    description: str
    params_model: type[StrategyParams]

    def __init__(self, params, data): ...
    def _setup(self): ...  # optional init
    @abstractmethod
    def rebalance_dates(self, start, end) -> list[date]: ...
    @abstractmethod
    def target_weights(self, ctx: StrategyContext) -> dict[str, float]: ...
    def fit(self, train_start, train_end) -> None: ...  # optional ML hook
```

Strategy parameters defined as Pydantic models; auto-serialize to JSON Schema for frontend; validated at the API boundary.

`StrategyContext` carries `as_of_date`, `universe`, `portfolio_value`, `current_weights`. Read-only.

### 4.4 Strategy 1: Multi-Factor Cross-Sectional, Sector-Neutral, Long-Only

**Flow per rebalance date:**
1. Universe filter: HSI members + liquidity filter ($1M USD median daily turnover) + feature-availability filter
2. Compute 10 features
3. Cross-sectional rank within sector → z-score
4. Average within family → 4 family scores
5. Weighted average across families → composite score
6. Select top `n_long` (default 20) proportional to sector representation
7. Equal-weight selected names; residual = cash

**Parameters:** `rebalance_frequency` (monthly/quarterly), `n_long` (10–40, default 20), `sector_neutral` (default True), `factor_weights` (default equal 0.25 each), `weighting_scheme` (equal/score-weighted, default equal), `liquidity_threshold_usd` (default $1M), `universe_id` (HSI).

**Explicit omissions for v1:** no risk model, no turnover-aware optimization, no regime conditioning, no imputation.

### 4.5 Strategy 2: Gradient Boosting on Factor Features

**Concept:** Same feature set as Strategy 1, but combines features via a learned non-linear model (LightGBM) instead of a fixed weighted average.

**Label:** 21-day forward **sector-neutralized** return.

**Training architecture:** expanding-window walk-forward with purged 5-fold CV inside each window for hyperparameter selection.

**Walk-forward windows:**
- Training warm-up: 4 years
- OOS evaluation window: 2 years
- Expanding training set across windows

**Hyperparameter grid (deliberately constrained, 24 combinations):**
```python
PARAM_GRID = {
    "num_leaves": [15, 31, 63],
    "learning_rate": [0.05, 0.1],
    "n_estimators": [200, 500],
    "min_child_samples": [20, 50],
    "feature_fraction": [0.7, 1.0],
    "bagging_fraction": [0.7, 1.0],
}
```

**Interview narrative:** "I limited hyperparameter search to a curated grid to reduce hyperparameter overfitting risk. Reported OOS performance is therefore more conservative than what extensive search would produce."

**Reported metric for CV:** mean IC (Spearman rank correlation between predicted and realized returns).

### 4.6 Backtesting Engine

**Built from scratch** (not vectorbt/Backtrader/Zipline).

**Why build it:** Cross-sectional, PIT-aware, sector-neutralized factor backtesting with HK-specific costs doesn't fit external libraries cleanly. They're designed primarily for time-series-per-asset workflows. Building it ourselves matches the industry pattern (real quant shops have in-house backtesters) and demonstrates quant rigor.

**Components:**
- `BacktestEngine` — the loop
- `Portfolio` — tracks cash, holdings, history
- `CostModel` — applies transaction costs
- `Trade` and `ExecutedTrade` — value objects
- `BacktestResult` — final container

**Conventions:**
- **Execution timing:** same-day close with one-day signal lag. Strategy uses data through D-1; trades execute at close of D
- **Trading calendar:** HKEX via `exchange-calendars` library
- **Fractional shares:** allowed in v1; board lots deferred to Phase 2
- **PIT enforcement:** engine only ever passes `as_of_date = current_date`; DataSource rejects future-data requests

**Size estimate:** ~800–1200 lines of focused Python plus tests.

### 4.7 Cross-Validation Framework

**Walk-forward:** expanding-window. First window has training warm-up; subsequent windows extend training set.

**Purged k-fold** (within each training set):
- Default 5 folds
- For each fold's test set, **purge** training samples whose label window overlaps the test date range
- Additionally **embargo** a buffer (default 5 days) on both sides of the test set

**Why purged k-fold matters:** Standard time-series CV doesn't address label leakage. If your label is 20-day forward return, and your training set contains a sample from date D, and your test set contains a sample from date D+5, then the training sample's label incorporates information from D+5. Purging removes this leakage. Without it, reported Sharpe ratios are systematically inflated.

**Reference:** López de Prado, *Advances in Financial Machine Learning* (2018), Ch. 7.

### 4.8 HK Transaction Cost Model

**Per-trade cost components (in basis points):**

| Component | Bps | Side |
|---|---|---|
| Commission (institutional) | 2.0 | Both |
| Stamp duty | 10.0 | Sell only |
| SFC transaction levy | 0.27 | Both |
| HKEX trading fee | 0.5 | Both |
| CCASS settlement | 0.2 | Both |
| **Round-trip total** | **~16 bps** | |

**Slippage (separate, additive):** volume-aware, `slippage_bps = α × (trade_notional / median_daily_volume)^β`, defaults α=10, β=0.5.

All costs are parameters; user can override in UI for sensitivity analysis.

**Interview narrative:** Many backtests assume 5 bps round trip; ours assumes 16. This makes reported Sharpe lower but more credible.

### 4.9 Performance Analytics

**Summary metrics:** total/annualized return, vol, Sharpe, Sortino, Calmar, max drawdown (peak-to-recovery duration, not peak-to-trough), skew, kurtosis, worst/best month, % positive months, annualized turnover, avg holdings, total trades, total costs, cost drag, benchmark comparisons (alpha, beta, info ratio, tracking error).

**Time-series analytics:** equity curve, drawdown curve, rolling 1Y Sharpe, rolling 3M vol, holdings count, sector exposures, cumulative turnover, cumulative costs.

**Factor regression:** OLS regression of strategy returns on HK-specific MKT/SMB/HML/MOM factors. Factors constructed from our universe (top 30% minus bottom 30% on each characteristic, monthly rebalance). Reports betas, t-stats, R², alpha (annualized).

**IC reporting (Strategy 2):** per-rebalance IC, mean IC, IC std, IC IR (mean/std), cumulative IC plot over time.

**Methodological standards:**
- Sharpe from daily returns annualized
- Max drawdown duration = peak-to-recovery
- Newey-West t-stats deferred to Phase 2

### 4.10 MLflow Integration

**Self-hosted MLflow Tracking Server** as 7th deployment container. Backed by our Postgres (separate database) for metadata; local filesystem for artifacts.

**Per walk-forward window (Strategy 2):** one MLflow run logging:
- Parameters: strategy params, model hyperparams, feature set version, window dates, code git SHA
- Metrics: per-fold CV IC, mean/std/IR, training IC, feature importance
- Artifacts: trained model, feature importance plot, predicted-vs-actual scatter

`jobs.mlflow_run_ids` (JSONB) stores all MLflow run IDs used by a backtest, for full traceability.

**MLflow Model Registry not used in v1** — too much ceremony for our scale.

### 4.11 Model Storage and Caching

- Models serialized as LightGBM files, stored as MLflow artifacts (filesystem-backed)
- Backtester loads models by MLflow run_id
- **Model cache:** before training, check MLflow for an existing run with matching `(strategy_id, params_hash, window_id, code_version, data_provider)`. If found, load instead of retrain.

### 4.12 Hard-to-Reverse Decisions

1. Feature interface and registry pattern
2. Strategy interface (ABC + Pydantic params)
3. PIT enforcement at engine and DataSource layers
4. Purged k-fold + walk-forward as the training regime
5. MLflow as experiment tracking
6. HK transaction cost model as default

---

## 5. API & Backend Design

### 5.1 Architectural Principles

- **REST** over GraphQL/gRPC. Single client (our frontend), no service-to-service RPC, REST + OpenAPI is the right fit.
- **Open-by-default for read access.** Anyone can browse strategies, see methodology, view showcase backtests.
- **Rate-limited execution.** Backtest creation is open but rate-limited per IP.
- **HTTP Basic Auth at caddy for admin endpoints.** Single admin user (env-configured).
- **Path-prefix versioning.** All endpoints under `/api/v1/...`.
- **OpenAPI documentation is a deliverable, not an emergent artifact.**

**No user accounts in v1 or v2.** Open access is a deliberate product choice for the educational positioning. Phase 3 if needed.

### 5.2 Endpoint Catalog

```
# Operational
GET    /api/v1/health
GET    /api/v1/version

# Strategies
GET    /api/v1/strategies
GET    /api/v1/strategies/{strategy_id}
GET    /api/v1/strategies/{strategy_id}/params-schema

# Universes
GET    /api/v1/universes
GET    /api/v1/universes/{universe_id}/members?as_of_date=...

# Features (introspection)
GET    /api/v1/features
GET    /api/v1/features/{feature_name}

# Backtests
POST   /api/v1/backtests
GET    /api/v1/backtests/{job_id}
GET    /api/v1/backtests/{job_id}/result
GET    /api/v1/backtests/{job_id}/equity-curve
GET    /api/v1/backtests/{job_id}/holdings
GET    /api/v1/backtests/{job_id}/trades
DELETE /api/v1/backtests/{job_id}
GET    /api/v1/backtests

# Showcase (pre-computed reference backtests)
GET    /api/v1/showcase
GET    /api/v1/showcase/{showcase_id}

# MLflow integration (read-only proxy)
GET    /api/v1/ml/runs?strategy_id=...
GET    /api/v1/ml/runs/{mlflow_run_id}

# Admin (HTTP Basic Auth)
POST   /api/v1/admin/ingest/free-prices
POST   /api/v1/admin/showcase/recompute
GET    /api/v1/admin/jobs/stats
```

### 5.3 Schemas

- All Pydantic-modeled, validated at the API boundary
- All endpoints declare `response_model=...` for OpenAPI completeness
- Backtest creation validates `params` against the strategy's registered Pydantic params model
- Business rules enforced (date range minimums, capital ranges, Strategy 2 history requirements)
- Result payloads split: full result, equity curve only, holdings only, trades only — to avoid 5MB JSON for views needing 50KB
- **Strategy methodology lives in markdown files in the repo** under `azureus/strategies/docs/`, loaded at startup; not in the database

### 5.4 Error Semantics

All errors return:
```python
{
  "error": {
    "code": "MACHINE_READABLE_CODE",
    "message": "Human-readable explanation",
    "details": { ... },
    "request_id": "uuid"
  }
}
```

Error code catalog: 400 INVALID_REQUEST · 401 UNAUTHORIZED · 403 FORBIDDEN · 404 STRATEGY_NOT_FOUND/JOB_NOT_FOUND/RESULT_NOT_AVAILABLE · 409 JOB_NOT_CANCELLABLE · 422 VALIDATION_ERROR/BUSINESS_RULE_VIOLATION · 429 RATE_LIMITED · 500 INTERNAL_ERROR · 503 SERVICE_UNAVAILABLE.

500s log full stack trace, request context, timing — correlated by `request_id`.

### 5.5 Observability

**Logs:** structured JSON to stdout, captured by Docker.
**Metrics:** Prometheus-format endpoint at `/metrics`.
**Tracing:** deferred (monolithic architecture).
**Grafana:** deferred (metrics endpoint exists; dashboard is Phase 2).
**APM/Sentry:** deferred.

### 5.6 Rate Limiting

`slowapi` middleware backed by Redis. Sliding-window per IP.

- `POST /api/v1/backtests`: **5 per hour per IP**
- All other endpoints: **120 per minute per IP** (defensive default)

429 response with `Retry-After` header.

### 5.7 OpenAPI Documentation

Auto-generated by FastAPI, served at `/api/v1/docs` (Swagger) and `/api/v1/redoc`. Pydantic models include examples. All endpoints have meaningful descriptions. Treated as a portfolio artifact.

### 5.8 Hard-to-Reverse Decisions

1. REST over GraphQL
2. No user accounts in v1 or v2
3. Path-prefix versioning (`/api/v1/`)
4. Error response shape

---

## 6. Frontend

### 6.1 Architecture

- **Vite + React 18+** as the build/runtime stack
- **Multi-page SPA** with client-side routing
- **TanStack Router** for type-safe routing
- **TanStack Query** for all server state (caching, polling, refetching, retries)
- **Zustand** for UI-only state

**Why Vite + React SPA over Next.js:** Our backend is the API surface; Next.js's API routes would compete with FastAPI. SEO requirements are minimal. One less framework and container to maintain. The judgment about *why* you chose Vite (focused scope, FastAPI handles server concerns) is itself a senior signal.

**Why TanStack Query:** Built-in `refetchInterval` for job status polling. Modern, current-job-market relevant. Handles HTTP caching, polling, refetching, retries automatically.

### 6.2 Page Structure

Six routes:
- `/` — Landing
- `/strategies` — Strategy gallery
- `/strategies/:strategy_id` — Strategy detail (Methodology / Showcase / Run Your Own tabs)
- `/backtests/:job_id` — Backtest result (shareable URL)
- `/methodology` — Cross-cutting methodology writeup
- `/about` — About the project and author

The strategy detail page is the centerpiece. The methodology page is the principal quant-rigor surface.

### 6.3 Design System

- **shadcn/ui** components (Radix UI primitives + Tailwind, copied into codebase)
- **Tailwind CSS** for utility styling
- **Color palette:** muted, professional, slate/neutral base with azure-blue accent matching the domain identity
- **Typography:** Inter (UI), JetBrains Mono (numerical displays, code)
- Mono fonts mandatory for financial figures

### 6.4 Component Organization

```
src/
  components/
    ui/              # shadcn primitives
    charts/          # Plotly-based domain charts (8 specified)
    layout/          # Header, Footer, Sidebar
    strategy/        # Strategy-related composites
    backtest/        # Backtest-related composites
  pages/             # one component per route
  hooks/             # useBacktestPolling, useStrategyMetadata, useShowcase
  api/               # axios/fetch wrappers per resource
  stores/            # Zustand stores (UI state only)
  types/             # TS types matching backend Pydantic
  utils/             # formatting, dates
```

**Hand-built dynamic params form** (driven by JSON Schema from API), not a library like RJSF. ~200 lines, fully owned, supports our parameter shapes.

### 6.5 Job Polling Pattern

TanStack Query handles backtest job polling:
- `useBacktestStatus(jobId)` polls every 2 seconds; auto-stops on terminal status
- `useBacktestResult(jobId, enabled)` fetches the full result only when status is `done`; cached forever
- URLs are state — closing and reopening the tab works
- Toast notifications deferred to Phase 2

### 6.6 Data Visualization

**Plotly.js** (via react-plotly.js).

Eight chart components:
1. `EquityCurve` — strategy vs. benchmark, log-scale toggle, range slider
2. `DrawdownChart` — underwater plot, red intensity scaled to depth
3. `RollingMetricsChart` — stacked 1Y Sharpe / 3M vol
4. `SectorExposureStacked` — stacked area, weight over time
5. `FactorExposureHeatmap` — beta heatmap, factor × time period
6. `ICTimeSeries` — Strategy 2 only, bars + 12M rolling mean
7. `HoldingsTable` — sortable/searchable/paginated
8. `SummaryMetricsGrid` — card grid of 8–12 scalar metrics

**Why Plotly over Recharts/visx:** Plotly's financial-terminal aesthetic matches the domain. Built-in interactivity (zoom, range sliders) for free. Python/JS sibling libraries allow shared chart specs between research notebooks and frontend.

### 6.7 Responsive and Accessibility

- **Desktop-first, mobile-functional.** Tailwind breakpoints
- **Basic accessibility:** semantic HTML, keyboard navigation, sufficient contrast, alt text. Not WCAG-compliant

### 6.8 Hard-to-Reverse Decisions

1. SPA architecture
2. TanStack Query as the server state layer
3. shadcn/ui design system
4. Plotly as the chart library
5. URL-driven backtest pages (`/backtests/:job_id`)

---

## 7. DevOps & Infrastructure

### 7.1 Container Topology (7 services)

Single DigitalOcean droplet, $24/month tier (2 vCPU, 4 GB RAM, 80 GB SSD):

1. **caddy** — TLS termination, reverse proxy, serves frontend static files
2. **api** — FastAPI + uvicorn
3. **worker** — Python RQ worker
4. **redis** — job queue + cache
5. **postgres** — primary store with TimescaleDB extension
6. **prefect** — orchestration server for ingestion pipelines
7. **mlflow** — experiment tracking server

API and worker share a base Docker image (`azureus-base`). Frontend builds to static files in CI and is served by Caddy via a mounted volume.

**Resource expectations:** ~1.3 GB idle (all 7 containers), ~3.0 GB peak (Strategy 2 training). Phases 0–3 fit on B1S (1 GB) by running only the subset of containers needed per phase. Phase 4+ requires B2s (4 GB) — Strategy 2 training is the resize trigger.

### 7.2 Local vs. Production

**Local dev:** native Vite dev server on port 5173 + Docker Compose for backend services. Caddy not needed locally. Frontend proxies `/api/*` to api container.

**Production:** all 7 containers via `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d`. Caddy serves 80/443. Internal ports not exposed.

### 7.3 Secrets and Configuration

Three layers:
- `.env.example` — committed, documents required variables
- `.env` — gitignored, local-dev values
- `/etc/azureus/.env.production` on droplet — chmod 600, owned by deploy user

Sensitive values (POSTGRES_PASSWORD, APP_SECRET_KEY, ADMIN_PASSWORD_HASH) generated once during initial deployment; stored only in production .env and password manager. No external secrets manager.

### 7.4 CI/CD with GitHub Actions

Three workflows:

**`ci.yml`** (every push and PR): ruff, mypy, pytest, pnpm lint/typecheck/test, frontend build, Docker image build verification. Target <5 min.

**`deploy.yml`** (push to main): build images, push to GHCR, SSH to droplet, pull and restart, run Alembic migrations, health check.

**`scheduled.yml`** (cron): daily free-data ingestion, weekly DB validation.

Branch model: `main` is always deployable; feature branches via PR; semver tags for milestones.

### 7.5 TLS and Domain

**Caddy** for TLS termination, reverse proxy, and static file serving. Automatic Let's Encrypt issuance and renewal via ACME. Caddyfile-based config.

**Why Caddy over nginx:** Automatic certificate management, no certbot maintenance, cleaner config, modern TLS defaults. The marginal "nginx on resume" signal isn't worth the operational overhead.

### 7.6 Backups

- **Postgres:** daily `pg_dump`, compressed, uploaded to Azure Blob Storage (Hot tier; well under the 5 GB free quota at our scale). Retained 30 days
- **MLflow artifacts:** weekly upload to Azure Blob Storage
- **Production `.env`:** password manager
- Restore procedure: `docs/disaster-recovery.md`

### 7.7 Monitoring

- **UptimeRobot** (free tier): pings `/api/v1/health` every 5 min
- **Disk usage:** cron alert at 80%
- **Container health:** Docker healthchecks + `restart: unless-stopped`
- **Logs:** `docker compose logs` + 90-day rotation

Prometheus metrics exposed at app layer but no Grafana dashboard in v1.

### 7.8 Deployment Process

Standard git-driven flow: commit → push → PR → CI green → merge → automatic deploy via GHA → health check. No manual SSH. Rollback via re-deploying a prior image tag.

### 7.9 Total Infra Cost

**Phases 0–3:** $0 (B1S free tier, Azure Blob Storage within free quota).
**Phase 4+:** ~$30/month (B2s VM upgrade for LightGBM training).
Azure for Students credit: $100 (covers ~3 months of B2s post-upgrade).
Net first-year out-of-pocket: ~$200, primarily Azure VM costs after credit exhausts.

### 7.10 Hard-to-Reverse Decisions

1. Single-VM architecture (Azure for v1)
2. Caddy as TLS terminator
3. GHCR for images
4. Postgres in a container (not managed DB)

---

## 8. Code Quality, Testing, Documentation

### 8.1 Code Style

**Python:** `ruff` (lint + format), `mypy` (strict on new code), type hints universal, Google-style docstrings. Single `pyproject.toml`.

**TypeScript:** `eslint` + `@typescript-eslint`, `prettier`, `tsc --noEmit` in CI, `"strict": true` in tsconfig. No `any` without justification.

**Pre-commit hooks** via `pre-commit` framework.

### 8.2 Testing Strategy

Integration-weighted pyramid (not classical unit-heavy):

- **Unit:** features, cost model, performance metrics, purged k-fold splitter, date utilities
- **Integration:** DataSource against test Postgres, migrations, end-to-end backtester runs on synthetic data, job queue lifecycle, **PIT correctness regression test** (AuditingDataSource)
- **E2E:** API via `httpx.AsyncClient` against full stack — happy + error paths
- **Frontend:** Vitest for components/hooks, Playwright for 1–2 critical flows

**Coverage targets:** 90% for core logic, path-coverage for API, ~50% for frontend.

**The no-lookahead regression test** is the project's signature test, explicitly highlighted in README and methodology page.

### 8.3 Documentation

Three documents for three audiences:
1. **README** — visitor-facing, screenshots, quickstart
2. **Methodology page** (`azureus.tech/methodology`) — the substance document
3. **`docs/ARCHITECTURE.md`** — this document

Plus: per-strategy markdown, OpenAPI at `/api/v1/docs`, `docs/RUNBOOK.md`, `CLAUDE.md` for Claude Code consumption.

**Principle:** code + tests + docs = done. Otherwise = incomplete.

### 8.4 Git Workflow

Conventional Commits, PR template, self-reviewed PRs, squash merge to main, semver tags for milestones.

---

## 9. Build Order & Milestones

### 9.1 Build Order Principles

P1. Vertical slices, not horizontal layers
P2. Deploy early (Phase 0)
P3. Data correctness before model sophistication
P4. Backtester before strategies
P5. Iterate visibly — every phase ends demoable
P6. Free data path before Bloomberg (proves DataSource abstraction)
P7. ML in Phase 4, not Phase 1

### 9.2 Phase Structure

| Phase | Days | Goal | Success Criterion |
|---|---|---|---|
| **0 Foundation** | 1–4 | Repo, CI/CD, deployment pipeline, Hello World on `azureus.tech` | Stranger visits site, sees working page; CI badge green; one-line change deploys |
| **1 Data Layer** | 5–14 | Schema, DataSource, YFinance ingestion, Pandera, AuditingDataSource, 10y data | Script queries any HSI ticker over any 10y range, gets clean PIT-correct data |
| **2 Backtester + Benchmark** | 15–22 | Engine, Portfolio, HKCostModel, calendar, Strategy 0, analytics | One-line command produces 10y benchmark backtest matching HSI total return |
| **3 Strategy 1 + API + Frontend** | 23–34 | Features, Strategy 1, full API, RQ, TanStack Query, all 8 charts, deploy to prod | User on `azureus.tech` runs custom Strategy 1 backtest end-to-end. **v1 MVP** |
| **4 Strategy 2 + MLflow** | 35–44 | Purged k-fold, walk-forward, LightGBM, MLflow container, IC viz | Strategy 2 backtest end-to-end in 10–20 min; realistic mean IC; MLflow UI live |
| **5 Bloomberg + Factor Reg + Polish** | 45–55 | BBG ingestion, comparison analysis, HK factor portfolios, factor regression, polish | Site interviewer-ready; methodology page complete; BBG strategies locally runnable |
| **Buffer** | 56–60+ | Slippage absorption, docs gaps, demo video | — |

### 9.3 Anti-Procrastination Mechanisms (Committed)

**Mechanism 1: Binary Phase Exit Criteria.** Phases do not transition until success criterion met. No silent drift.

**Mechanism 2: Weekly Check-ins.** Every 7 days: (1) finished, (2) slipped, (3) plan. Vague answers get pushed back.

**Mechanism 3: The 2-Day Rule.** Stuck for 2 working days with no measurable progress = stop and triage. Three diagnoses: scope wrong, approach wrong, knowledge gap.

**Mechanism 4: Phase-Level Hard Deadlines.** Overall project flexible; phase completion order and individual phase deadlines are not. Adjusting requires explicit conversation that changes scope or timeline — never both silently.

### 9.4 Known Risks

1. **Phase 1 highest-risk.** Real data surfaces surprises. Budget full 10 days; escalate at 14
2. **Phase 4 second-highest.** Fallback: simpler CV with documented compromise
3. **Bloomberg lab access in Phase 5.** Check lab schedule in Phase 0
4. **Phase 3 largest (12 days).** Slip compresses downstream; Phase 3 alone ships a v1, so total project survives a slip

### 9.5 Hard-to-Reverse Decisions

1. Free data path before Bloomberg
2. Backtester before strategies
3. Phase 3 as MVP cutoff

---

## Appendix A: Hard-to-Reverse Decisions (Master List)

These are the decisions where changing course later is genuinely expensive. Get them right now or pay later.

**Domain & Product:**
- Educational positioning (not research tool, not practitioner tool)
- HK equities universe in v1
- Research-only scope (no live data, no execution)
- Data abstraction layer from day one
- Strategy interface from day one
- Monorepo, multi-Dockerfile
- MIT license, public repo
- Single VM for v1

**System Architecture:**
- Async job queue universally
- Modular monolith with shared codebase
- FastAPI as framework
- Postgres + TimescaleDB as primary store

**Data Architecture:**
- PIT modeling with explicit reported_date columns
- Provider as column, not schema
- Long-format fundamentals
- TimescaleDB hypertables on prices and macro
- Prefect for orchestration

**ML Platform:**
- Feature interface and registry pattern
- Strategy interface (ABC + Pydantic)
- PIT enforcement at engine and DataSource layers
- Purged k-fold + walk-forward training regime
- MLflow as experiment tracking
- HK cost model as default

**API & Backend:**
- REST over GraphQL
- No user accounts in v1 or v2
- Path-prefix versioning (`/api/v1/`)
- Error response shape

**Frontend:**
- SPA architecture
- TanStack Query as server state layer
- shadcn/ui design system
- Plotly as chart library
- URL-driven backtest pages

**DevOps:**
- Single-VM architecture
- Caddy as TLS terminator
- GHCR for images
- Postgres in container (not managed)

**Build Order:**
- Free data path before Bloomberg
- Backtester before strategies
- Phase 3 as MVP cutoff

---

## Appendix B: Explicit Non-Goals

Things this project deliberately is not, will not be, and should not drift toward.

- **Not a trading system.** No order execution, no broker integration
- **Not a real-time platform.** No streaming, no live signals in v1
- **Not a multi-tenant product.** No user accounts in v1 or v2
- **Not a derivatives platform.** Equities only
- **Not a low-latency system.** Latency irrelevant
- **Not a code-execution platform.** No user-uploaded strategies in v1 or v2
- **Not competing with vectorbt / Backtrader / QuantConnect.** Different audience, different category
- **No microservices, no k8s, no Kubernetes.** Single-droplet monolith
- **No managed databases.** Postgres in container
- **No paid observability (Datadog, New Relic).** Lightweight self-hosted only
- **No staging environment.** Local + production
- **No multi-region.** Single droplet
- **No Tier 1 enterprise frameworks (Airflow, k8s, service mesh).** Modern lightweight stack
- **No GraphQL.** REST
- **No Next.js.** Vite SPA
- **No exhaustive WCAG accessibility.** Basic only

---

## Appendix C: Deferred Decisions

Decisions explicitly *not* made now, scheduled for later phases.

**Phase 2 (post-v1):**
- Strategy 3: DL signal architecture choice
- Strategy 4: paper implementation selection
- Composability layer (compose strategies from primitives, no code execution)
- Universe expansion (HSCEI, mid-caps)
- Walk-forward hyperparameter optimization
- Long-short strategy variants
- Board-lot share rounding
- HK-specific factor risk model
- Newey-West t-stats for alpha
- Imputation strategies for missing fundamentals
- Combinatorial Purged CV (CPCV)
- Toast notifications for job completion
- Server-Sent Events for intra-backtest progress
- Dark mode
- Grafana dashboards
- Sentry error tracking
- i18n / Chinese localization

**Phase 3 (aspirational):**
- Sandboxed user-supplied strategy code
- Live signal generation
- Paper trading
- Multi-market support
- User accounts
- Managed Postgres
- Multi-region deployment

**Conditional (decided during implementation):**
- BLPAPI vs. Excel for Bloomberg ingestion — depends on lab capabilities, confirmed in Phase 0
- Specific Bloomberg field names per fundamental metric — iterate during ingestion development
- Specific Pandera rule details — iterate as data quirks emerge

---

**End of architecture document. Total decisions locked: 9 sections, 4 anti-procrastination mechanisms, ~50 hard-to-reverse decisions, ~20 deferred decisions.**
