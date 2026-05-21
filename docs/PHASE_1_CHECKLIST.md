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

- [x] Refactored `ingest_prices_free.py`: extracted `_ingest_one_ticker` helper that never raises and always writes one lineage row — shared with batch flow so per-ticker lineage semantics are uniform
- [x] `azureus/pipelines/ingest_prices_batch.py` — fan-out via `ThreadPoolExecutor(max_workers=concurrency)` (default 4). Returns `success` / `partial` / `failed` summary; raises only when every ticker fails
- [x] `azureus/pipelines/ingest_tickers_free.py` — name-only refresh from yfinance; **does NOT touch sector/industry** (CSV remains authoritative per Day 9). One lineage row per invocation with per-ticker failures in `errors.failures` JSONB
- [x] CLI entries for both: `python -m azureus.pipelines.ingest_prices_batch --all-active` / `--tickers ... --concurrency N` and `python -m azureus.pipelines.ingest_tickers_free`
- [x] `tests/test_ingest_prices_batch.py` — 5 tests: success, partial-failure, all-fail (raises), no-tickers noop, `is_active` filter
- [x] `tests/test_ingest_tickers_free.py` — 3 tests: name refresh + sector untouched, per-ticker failure lineage, active-filter default
- [x] Idempotency under overlapping ranges already covered by `ON CONFLICT DO UPDATE` on `pk_prices` (Days 7–8); batch tests verify this at scale

**Locked decisions on this PR:**
- Concurrency default = 4 (configurable). Empirically polite for yfinance at our ~70-ticker scale.
- Per-ticker lineage rows; no batch-level row (would be redundant — query the per-ticker rows by `started_at` proximity if you need batch grouping).
- No in-run retries. Failures surface immediately on the per-ticker `ingestion_runs` row; next scheduled invocation re-attempts. Idempotency comes from the PK ON CONFLICT.
- Batch flow raises only on **total** failure (all tickers fail). Partial failures return a summary normally so a single bad ticker doesn't abort the daily run.
- Ticker refresh is name-only. CSV remains authoritative for `sector` / `industry` / `currency` / `listed_date` until Phase 5 Bloomberg replaces it.

---

## Day 12 — `AuditingDataSource` + PIT regression test

- [x] `azureus/data/sources/auditing.py` — drop-in `DataSource` wrapper. Audits `get_fundamentals` against `reported_date <= as_of_date`. Raises `LookaheadError` (subclasses `AssertionError`) with a sample of violating rows. `get_prices` / `get_macro` / `get_universe_history` pass through (no PIT signature today; expand when the Protocol or use-cases evolve)
- [x] `tests/test_pit_regression.py` — **the project's signature methodology test**. 7 tests: honest source passes, leaky source raises, 13-month synthetic backtest walk (zero violations, exact row counts per rebalance date), `get_prices` passthrough, empty response, provider-name wrap, `get_universe` passthrough
- [x] Synthetic PIT corpus inline: 2 tickers × 4 quarterly statements in 2024 (plus Q4-2023) with realistic ~60-day disclosure lag

**Locked decisions on this PR:**
- Day 12 audit is **`get_fundamentals` only**. `get_macro` doesn't take `as_of_date` in the current Protocol; auditing it would either require Protocol changes or stateful `set_as_of()` on the wrapper. Both deferred until macro ingestion lands.
- `LookaheadError` subclasses `AssertionError` (not `RuntimeError`) — this is a methodological-correctness failure, not an operational one. Backtests that hit it have produced invalid results.
- Diagnostic counters (`fundamentals_calls`, `lookahead_violations`) so tests can assert the audit actually fired.
- In-memory fakes (`InMemoryFundamentalsSource`, `LeakyFundamentalsSource`) live in the test module — not promoted to the package, no other consumers yet.

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
