# Phase 1 Checklist — Data Layer (Days 5–14)

> Goal: a script can query any HSI ticker over any 10y range and receive clean, PIT-correct data through the `DataSource` interface.
>
> Risk: Phase 1 is the highest-risk phase per `docs/ARCHITECTURE.md` §9.4. Budget the full 10 days; escalate at 14.

---

## Day 5 — Schema + Alembic (this PR)

- [x] `azureus/config.py` — pydantic-settings reading `.env`
- [x] `azureus/data/db.py` — `Base`, `MetaData`, naming convention
- [x] `azureus/data/models.py` — 9 SQLAlchemy ORM models for §3.5 tables
- [x] `alembic/` scaffolded (init), `alembic/env.py` customized for our metadata + config
- [x] `alembic/versions/0001_initial_schema.py` — tables, TimescaleDB hypertables, §3.6 indexes
- [x] `tests/test_migrations.py` — apply / downgrade / re-apply against ephemeral DB
- [x] Migration runs cleanly locally (`uv run alembic upgrade head` + tests pass)
- [ ] Commit + push, CI green
- [ ] Update `.env.example` if any new vars were added (already covered)

**Deferred to a later migration:** `feature_cache` hypertable (column set depends on Phase 3 feature-engineering work).

---

## Day 6 — DataSource Protocol + DB engines + Pydantic schemas

- [ ] `azureus/data/db.py` — add async (asyncpg) and sync (psycopg) engines + `AsyncSessionLocal`
- [ ] `azureus/data/schemas.py` — Pydantic models for internal data shapes (Price, MacroValue, Fundamental, UniverseMember, etc.) — distinct from ORM models
- [ ] `azureus/data/sources/base.py` — `DataSource` Protocol per §3.4 with every method (`get_universe`, `get_universe_history`, `get_prices`, `get_fundamentals`, `get_fundamentals_history`, `get_macro`, `list_available_tickers`, `list_available_metrics`)
- [ ] Smoke test: open async + sync sessions against the migrated DB, run `SELECT 1`

---

## Days 7–8 — `YFinanceDataSource` + Pandera + first ingestion

- [ ] Add `yfinance` to dependencies (locked stack table addition — confirm before adding)
- [ ] `azureus/data/sources/yfinance_source.py` — implements `DataSource` against our Postgres tables (reads from DB; ingestion populates them)
- [ ] Pandera schema for price DataFrames (`azureus/data/validators.py`): types, columns, nullability, `high >= low`, positive prices, no future dates, no duplicate `(provider, ticker, date)`
- [ ] `azureus/pipelines/ingest_prices_free.py` — Prefect flow (in-process; Prefect server container deferred to Phase 2): fetch yfinance bars for one HSI ticker, validate, upsert via `INSERT ... ON CONFLICT DO UPDATE`, write `ingestion_runs` row
- [ ] Test: ingest 30 days for `0700.HK`, query it back, assert clean data

---

## Day 9 — Universe membership + tickers seed

- [ ] `data/universe/hsi_membership.csv` — committed static CSV of HSI historical constituents (derived from Bloomberg; treated as Phase 1 reference data, NOT Bloomberg-sourced live data per Rule 7)
- [ ] `scripts/seed_tickers.py` and `scripts/seed_universe.py` — bulk-load reference data
- [ ] Document the residual survivorship-bias limitation of the free-source CSV in `azureus/data/sources/README.md`

---

## Days 10–11 — Ingestion at scale + lineage

- [ ] Extend `ingest_prices_free` to batch over the whole HSI universe with concurrency control (Prefect task map + rate limiting)
- [ ] `ingest_tickers` flow (weekly cadence) — refresh ticker metadata from yfinance
- [ ] Idempotency: re-running ingestion on overlapping date ranges must not duplicate or corrupt rows (covered by `ON CONFLICT DO UPDATE` on the `(provider, ticker, date)` PK)
- [ ] Failure handling: every exception path writes a row to `ingestion_runs` with status `failed` or `partial` and full context in `errors` JSONB. No silent swallows.

---

## Day 12 — `AuditingDataSource` + PIT regression test

- [ ] `azureus/data/sources/auditing.py` — wraps any `DataSource` and asserts that no row returned has `reported_date > as_of_date`
- [ ] `tests/test_pit_regression.py` — the signature PIT correctness test; runs `AuditingDataSource` over a synthetic backtest and asserts zero lookahead. **This is the project's signature test** (mentioned in CLAUDE.md and the README methodology page once it exists).

---

## Day 13 — Historical load + completeness audit

- [ ] Load ~10 years of daily bars for the current HSI universe via `ingest_prices_free`
- [ ] Validate row counts per ticker: expect ≈ 2520 trading days × N tickers, with documented exceptions for late-listed names
- [ ] Spot-check obvious quality issues (zero-volume runs, price gaps, missing tickers)

---

## Day 14 — Validation flow + Phase 1 exit

- [ ] `azureus/pipelines/validate_db_state.py` — weekly Prefect flow that audits the full DB for invariant violations (gaps, duplicate PKs, FK violations, future-dated rows, etc.)
- [ ] Run it; resolve any findings or document as known limitations
- [ ] **Phase 1 exit criterion:** one-line script (or `uv run` command) queries any HSI ticker over any 10y range via `DataSource.get_prices(...)` and returns clean PIT-correct data. Verified by AuditingDataSource wrapper.

---

## Anti-procrastination

- 2-Day Rule applies. Stuck for two working days with no measurable progress = stop and triage (scope vs. approach vs. knowledge gap).
- Real data surfaces surprises. Don't optimize ingestion prematurely. Get to "1 ticker × 30 days, end-to-end" first; scale after.
- yfinance is rate-limited and unreliable. Expect to retry, cache, and fail gracefully. Document quirks in `azureus/data/sources/README.md` as you find them.

---

## What Phase 2 will need on Day 15

You don't need to do these in Phase 1, but knowing they're coming:

- HKEX trading calendar via `exchange-calendars`
- `BacktestEngine`, `Portfolio`, `HKCostModel`, `BacktestResult`
- Strategy 0 (HSI market-cap-weighted benchmark)
- Performance analytics (Sharpe from daily returns, peak-to-recovery drawdown, etc.)

Don't pre-build any of this in Phase 1.
