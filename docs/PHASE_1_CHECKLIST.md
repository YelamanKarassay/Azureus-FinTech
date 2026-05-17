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
- [x] Commit + push, CI green (run 25713708892, 2026-05-12)
- [x] `.env.example` updated — switched to `localhost` hostnames for host-side dev

**Deferred to a later migration:** `feature_cache` hypertable (column set depends on Phase 3 feature-engineering work).

---

## Day 6 — DataSource Protocol + DB engines + Pydantic schemas

- [x] `azureus/data/db.py` — async (asyncpg) and sync (psycopg) engines, sessionmakers, `async_session` / `sync_session` context managers (lazy via `lru_cache` so imports don't fail without env vars)
- [x] `azureus/data/schemas.py` — Pydantic v2 frozen models: `TickerMetadata`, `PriceBar`, `Fundamental`, `MacroValue`, `UniverseMember`
- [x] `azureus/data/sources/base.py` — `DataSource` Protocol per §3.4 with every method, plus locked return-shape convention (long DataFrames for time-series, `list[str]` for reference)
- [x] Smoke test: `tests/test_db_connection.py` — 3 tests (sync `SELECT 1`, async `SELECT 1`, timescaledb extension check); auto-skips without `DATABASE_URL_SYNC`
- [x] Dependency additions: `sqlalchemy[asyncio]` extra (pulls `greenlet`), `pandas-stubs` dev dep

**Locked decisions on this PR:**
- DataSource time-series methods return long-format `pd.DataFrame`; reference methods return `list[str]`; PIT fundamentals snapshot returns long-format `pd.DataFrame`.
- Engines/sessions are lazy `lru_cache` factories so module imports never fail on env-less environments.

---

## Days 7–8 — `YFinanceDataSource` + Pandera + first ingestion

- [x] Added `yfinance>=0.2.50` and `prefect>=3.1` (both pre-sanctioned in ARCHITECTURE §3.3 / Stack table)
- [x] `azureus/data/sources/yfinance_source.py` — `YFinanceDataSource` (read) + `fetch_prices_from_yfinance` (write helper). Phase 1 stubs raise `NotImplementedError` for fundamentals / macro / metrics
- [x] `azureus/data/validators.py` — `PRICES_SCHEMA` Pandera DataFrameSchema: types, providers whitelist, `high >= low`, positive prices, `Int64` volume, no future dates, no duplicate `(provider, ticker, date)`, strict columns
- [x] `azureus/utils/reproducibility.py` — git SHA, git_status_clean, uv.lock hash for `ingestion_runs.config`
- [x] `azureus/pipelines/ingest_prices_free.py` — Prefect 3 flow with `@flow`/`@task` decorators (in-process, no server). Fetch → Pandera validate → `INSERT ... ON CONFLICT (pk_prices) DO UPDATE`. Always writes one `ingestion_runs` row, even on failure.
- [x] `tests/conftest.py` — shared `ephemeral_database` and `migrated_database` fixtures, `prefect_test_harness` auto-use, synthetic prices DataFrame
- [x] `tests/test_validators.py` — 8 Pandera unit tests (clean df + 7 negative cases)
- [x] `tests/test_ingest_prices_free.py` — 4 E2E tests: success path, idempotency on re-ingest, failure-path lineage row, DataSource read-back

**Locked decisions on this PR:**
- Internal canonical ticker format: `0700.HK` (yfinance form). Bloomberg translation deferred to Phase 5.
- yfinance `auto_adjust=False` → raw OHLC plus `adjusted_close` column. Adjusted close is canonical for return calculations (§4.6).
- Rows with null `close` are dropped at the fetch layer; we never persist a bar without a close.
- Prefect server container deferred to Phase 2; flows run in-process. Tests use `prefect_test_harness` (ephemeral SQLite).
- `pytest.PytestUnraisableExceptionWarning` ignored in `pyproject.toml` — async-engine cleanup at process exit is unreliable; production code uses async context managers that close cleanly.

---

## Day 9 — Universe membership + tickers seed

- [x] `data/universe/tickers.csv` (69 names) + `data/universe/hsi_members.csv` (69 rows) — Option B per Day 9 plan: current HSI members + 12 known late additions with HK listing dates as start_date
- [x] `scripts/seed_tickers.py` and `scripts/seed_universe.py` — idempotent UPSERT via `ON CONFLICT`, exposed as `python -m scripts.<name>` with `--csv` flag
- [x] `azureus/data/sources/README.md` — documents the survivorship-bias limitation, the listing-date-as-start-date convention for late additions, yfinance HK quirks, and the fundamentals/macro deferral
- [x] `tests/test_seed_scripts.py` — 7 tests: mechanism (fixture CSVs), idempotency, FK enforcement, and smoke-tests against the real curated CSVs (asserts `≥60` rows + spot-checks 0700.HK / 0005.HK / 3690.HK / 9988.HK)

**Locked decisions on this PR:**
- Universe scope is **Option B**: current snapshot + known late-additions with HK listing dates. Names removed from HSI within the 10y window are NOT captured. Documented in `azureus/data/sources/README.md`.
- Late-addition `start_date` = HK listing date, NOT the exact HSI inclusion date (which we don't have authoritatively without Bloomberg).
- Sector taxonomy = GICS (matches yfinance / most free providers). HSI Industry classification cross-walk deferred to Phase 5.
- `scripts/` is a package (has `__init__.py`) so tests can import `from scripts import seed_tickers`. Operational scripts only; no public API.

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
