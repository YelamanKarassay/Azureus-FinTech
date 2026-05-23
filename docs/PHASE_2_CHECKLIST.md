# Phase 2 Checklist — Backtester + Benchmark (Days 15–22)

> **Goal (per ARCHITECTURE §9.2):** one-line command produces a 10-year benchmark backtest. Engine, Portfolio, HKCostModel, calendar, Strategy 0, and the performance-analytics suite — all written from scratch, no `vectorbt` / `backtrader` / `zipline`.
>
> **Why from scratch (per ARCHITECTURE §4.6):** cross-sectional, PIT-aware, sector-neutralized factor backtesting with HK-specific costs doesn't fit those libraries cleanly — they're per-asset time-series tools. Building it ourselves matches the industry pattern and demonstrates quant rigor. Size estimate: ~1000–1500 lines of focused Python + tests.

---

## Day 15 — Trading calendar + value objects

- [x] Added `exchange-calendars>=4.5` (ARCHITECTURE §4.6 sanctioned)
- [x] `azureus/utils/dates.py` — HKEX (XHKG) calendar helpers via `lru_cache`-singleton:
  - `is_trading_day(d)`, `trading_days_between(start, end)`, `next_trading_day(d)`, `previous_trading_day(d)`, `roll_to_trading_day(d)`
  - All operate on `dt.date`; internally use `sessions_in_range` because `next_session(d)` requires `d` to itself be a session (awkward for arbitrary-date lookups)
- [x] `azureus/backtesting/value_objects.py` — frozen Pydantic models:
  - `Trade` — ticker, signed shares, reference_price
  - `ExecutedTrade` — full HK cost breakdown (commission/stamp_duty/sfc_levy/hkex_fee/ccass_fee/slippage), total_cost, net_cash_change
  - `Position` — ticker, shares, last_price, market_value
  - `PortfolioSnapshot` — daily portfolio state for the equity curve
- [x] `tests/test_dates.py` — 15 tests: weekends, NYE 2024, LNY 2024, Christmas 2024, next/previous semantics, roll-to-trading-day on weekend/holiday/multi-day-holiday boundaries, inclusive-range, empty-range, parametrized holiday spot-checks
- [x] `tests/test_value_objects.py` — 6 tests: frozen-ness, signed shares, cost field preservation

**Locked decisions for this PR:**
- Trading calendar = HKEX (XHKG). Architecture-pinned; no other markets in v1.
- Fractional shares allowed (§4.6). Board-lot rounding deferred to v2.
- Holiday handling: rebalance dates on non-trading days roll forward to the next session.
- Signed-shares convention everywhere (positive=buy, negative=sell). V1 is long-only; `Portfolio` (Day 16) will enforce that negative shares can only close existing positions.
- Monetary values are HKD floats in-memory. NUMERIC precision discipline applies at the DB boundary.

---

## Day 16 — Portfolio

- [x] `azureus/backtesting/portfolio.py` — `Portfolio` class:
  - Properties: `cash`, `holdings` (read-only Mapping view), `history` (tuple)
  - `apply_executed_trade(trade)` — updates cash via `net_cash_change`, replaces Position; long-only enforced via `LongOnlyError` (atomicity: cash unchanged on failed apply)
  - `mark_to_market(prices)` — refreshes every Position; raises `KeyError` on missing price (engine bug if it happens)
  - `record_snapshot(as_of_date)` — appends frozen `PortfolioSnapshot` to history; `dict(self._holdings)` shallow copy isolates snapshots from later mutations
  - `total_value()` — cash + Σ market_value
  - `weights()` — implicit cash residual; returns `{}` when total_value ≤ 0
- [x] `tests/test_portfolio.py` — 19 tests: construction, buy/sell/accumulate/close/short-rejection/oversell-rejection, atomicity on failed trade, mark-to-market all-positions/missing-price/empty-portfolio, total value, weights with implicit cash, weights empty, snapshot capture, history accumulation, snapshot immutability under later mutation, history immutability under mark-to-market

**Locked decisions:**
- `LongOnlyError` (renamed from `LongOnlyViolation` to satisfy N818) subclasses `ValueError`. v1 is long-only; attempting to go short is a strategy bug, not a runtime condition.
- Cash implicit in `weights()` — sum of returned dict gives "fraction invested", remainder is cash. Strategies that need explicit cash weight can compute `1 - sum`.
- `last_price` updates to `fill_price` on `apply_executed_trade` (the trade itself observes a price); `mark_to_market` overwrites with the day's close. Between trades, the engine should mark to market.
- Trades arrive pre-executed: `apply_executed_trade` trusts `net_cash_change`. The cost model owns fee/slippage arithmetic.
- Negative cash allowed silently — the engine should size trades to avoid it; we don't enforce margin.

---

## Day 17 — Cost model

- [x] `azureus/backtesting/cost_model.py` — `HKCostModel` as `@dataclass(frozen=True)`. All seven params (5 bps fees + α + β) defaulted to ARCHITECTURE §4.8 values, override-able per instance
- [x] `execute(trade, fill_price, median_daily_volume, executed_at) -> ExecutedTrade` with every cost component broken out: `commission`, `stamp_duty` (sell-only), `sfc_levy`, `hkex_fee`, `ccass_fee`, `slippage`, `total_cost`, `net_cash_change`
- [x] **Fail-loud on illiquid names** — `median_daily_volume <= 0` raises `ValueError`. Strategies must filter illiquid names upstream
- [x] Zero-share edge case → zero-cost trade (no division-by-zero on slippage)
- [x] `tests/test_cost_model.py` — 16 tests (CLAUDE.md required cost-model assertions are tests 1–4):
  - Buy-side fees == HK$11.88 (2.97 bps × 40k) with each component checked individually
  - Sell-side fees == HK$51.88 (12.97 bps × 40k)
  - Round-trip == HK$63.76 ≈ 15.94 bps ≈ §4.8's "~16 bps"
  - Sell-side − buy-side == stamp_duty exactly
  - Slippage scales as √(notional/MDV) (4× ratio → 2× slip)
  - Concrete slippage value matches `10 × (10k/1M)^0.5 = 1 bp = HK$1.00`
  - Zero/negative MDV raises ValueError
  - Cash impact directionality (negative for buy, positive for sell-after-fees)
  - Param overrides flow through; frozen-dataclass guarantee

**Locked decisions:**
- All fees are bps of trade notional. No fixed minimums in v1.
- Slippage is symmetric in direction (no buy/sell asymmetry).
- HKD-only. Currency conversion costs would be a different model.
- `gross_notional == 0` → all-zero `ExecutedTrade`. Cheap, defensible default.

---

## Days 18–19 — BacktestEngine

- [ ] `azureus/backtesting/engine.py` — the main loop:
  - `BacktestEngine(strategy, data_source, cost_model, start, end, initial_capital)`
  - `run() -> BacktestResult`
  - For each rebalance date from `strategy.rebalance_dates(start, end)`:
    1. Mark portfolio to market using yesterday's close (one-day signal lag — Hard Rule 1 + §4.6)
    2. Call `strategy.target_weights(StrategyContext(as_of_date, ...))` with `as_of_date` strictly = simulation date
    3. Diff target weights vs current weights → list of `Trade`
    4. Each `Trade` → `ExecutedTrade` via cost model using today's close as fill price
    5. Apply executed trades to portfolio
    6. Record snapshot
  - Between rebalance dates: mark-to-market daily for the equity curve, no trades
- [ ] PIT enforcement: engine wraps the supplied `data_source` in `AuditingDataSource` by default (override-able for performance) — runtime PIT failure raises `LookaheadError` immediately, just like `tests/test_pit_regression.py`
- [ ] `tests/test_engine.py` — engine integration tests against synthetic-corpus DataSource:
  - Trivial buy-and-hold strategy → equity curve matches manual calculation
  - Strategy with multiple rebalances → cash flow + costs accounted for
  - Auditing wrapper catches a deliberately-leaky strategy

**Locked decisions:**
- Execution timing = same-day close with one-day signal lag. Signal computed from data through D-1; trades execute at D close (§4.6).
- Trading calendar drives the simulation step. Non-trading days are skipped entirely.
- Engine builds `StrategyContext` with `as_of_date`, current `universe`, `portfolio_value`, `current_weights` (read-only) per §4.3.
- Engine fails fast on missing prices for a target-weight ticker — strategy is expected to honor the liquidity filter.

---

## Day 20 — Metrics + BacktestResult

- [ ] `azureus/backtesting/metrics.py`:
  - `annualized_return(returns)` — geometric, daily returns annualized
  - `annualized_vol(returns)` — daily stdev × sqrt(252)
  - `sharpe(returns, rf=0)` — **from daily returns**, annualized (per CLAUDE.md "Common Mistakes" #2)
  - `sortino(returns, rf=0)`
  - `calmar(returns, max_dd)`
  - `drawdown_series(equity)` — running peak − current, normalized
  - `max_drawdown_with_duration(equity)` — returns `(depth, peak_date, trough_date, recovery_date, duration_days)`. **Peak-to-recovery duration** per CLAUDE.md "Common Mistakes" #3. If still under water, recovery_date is `None` and duration counts to last observation
  - `turnover(weight_series)`, `% positive months`, `skew`, `kurtosis`
- [ ] `azureus/backtesting/results.py` — `BacktestResult` Pydantic container:
  - `summary: dict[str, float]` — scalars
  - `equity_curve: pd.DataFrame` — date, total_value, daily_return
  - `holdings: pd.DataFrame` — date, ticker, weight, shares
  - `trades: pd.DataFrame` — executed trades with all cost components broken out
  - `as_dict()` → JSONB-serializable for `backtest_results.summary` etc.
- [ ] `tests/test_metrics.py` — known time-series produces known metrics:
  - Constant 1% daily return → Sharpe = (0.01 × 252) / (0 × sqrt(252)) = ∞ — assert sentinel handling
  - U-shaped drawdown of -20% → duration counts to actual recovery date
  - Synthetic returns with known stdev → annualized vol within rounding

**Locked decisions:**
- Daily returns are the input to all return-based metrics. Never monthly. Never weekly (per CLAUDE.md "Common Mistakes" #2 — this is non-negotiable).
- Max drawdown duration measures **peak-to-recovery**, not peak-to-trough.
- 252 trading days per year for annualization (industry standard for daily-bar series).
- Newey-West t-stats deferred to Phase 2-post-v1 per ARCHITECTURE §4.9 — skip.

---

## Day 21 — Strategy ABC + Strategy 0

- [ ] `azureus/strategies/base.py` — the locked `Strategy` ABC contract per ARCHITECTURE §4.3:
  - `id: str` class attribute
  - `name: str` class attribute
  - `description: str` class attribute
  - `params_model: type[StrategyParams]` — Pydantic, parameters defined per-strategy
  - `__init__(self, params: StrategyParams, data: DataSource)`
  - `_setup(self)` — optional override for one-time precomputation
  - `rebalance_dates(self, start, end) -> list[date]` — abstract
  - `target_weights(self, ctx: StrategyContext) -> dict[str, float]` — abstract
  - `fit(self, train_start, train_end) -> None` — optional, for ML strategies (Phase 4)
- [ ] `azureus/strategies/base.py` — `StrategyContext` Pydantic value object: `as_of_date`, `universe: list[str]`, `portfolio_value: float`, `current_weights: dict[str, float]` (frozen)
- [ ] `azureus/strategies/benchmark.py` — Strategy 0:
  - `EqualWeightedHSIBenchmark`
  - Rebalance quarterly on the first trading day of Jan/Apr/Jul/Oct
  - Target weights: equal-weight every HSI member returned by `data_source.get_universe('HSI', as_of_date)`
  - Documented deviation from true cap-weighted HSI — see "Open Question 2" below
- [ ] `azureus/strategies/registry.py` — central `_STRATEGIES` dict; `@register` decorator; `list_strategies()`, `get_strategy(id)`
- [ ] `tests/test_strategies_benchmark.py` — Strategy 0 unit tests:
  - Rebalance dates land on quarterly trading days
  - Target weights sum to 1.0 (within rounding)
  - Universe shrinks correctly when a member has no data (0011.HK should be excluded)

**Locked decisions:**
- Strategy interface is **stable** per CLAUDE.md Hard Rule 3. Future strategies = implement this interface. Modifying it = explicit architectural change.
- Strategy 0 = equal-weighted, not market-cap-weighted, in v1. Documented deviation. Cap-weighting deferred to Phase 5 when Bloomberg gives us shares-outstanding for market-cap calculation.
- Rebalance cadence = quarterly. Matches HSI's own quarterly reviews.

---

## Day 22 — End-to-end run + Phase 2 exit

- [ ] `scripts/run_benchmark_backtest.py` — CLI to run Strategy 0 over a date range:
  ```
  uv run python -m scripts.run_benchmark_backtest \
      --start 2014-01-01 --end 2026-05-22 \
      --initial-capital 1000000
  ```
  Outputs: summary metrics to stdout, optionally writes `BacktestResult` JSON to disk
- [ ] **Golden-output regression test** per CLAUDE.md "Required tests":
  - `tests/test_benchmark_regression.py` — runs Strategy 0 on the deterministic synthetic corpus (built in conftest from a fixed seed), asserts known Sharpe / max-drawdown / total-return within tolerance
  - This test is the canary for the engine: if it changes, somebody changed the engine semantics
- [ ] Sanity-check the live run against the actual HSI index:
  - Ingest `^HSI` via `ingest_prices_batch --tickers ^HSI` (or document why yfinance won't accept ^HSI for HK index)
  - Compare Strategy 0's equity curve to `^HSI` total return over the same window
  - Annualized return should be in the same ballpark (HSI averaged ~5–8% over 2014–2024 per public data); document the gap given equal-weighting bias
- [ ] **Phase 2 exit criterion (per ARCHITECTURE §9.2):** the one-line command above produces a 10y benchmark backtest. Annualized return / Sharpe / max DD all reported. Golden regression test green.

---

## Open questions to settle before Day 21

These are real choices, not nits. Resolving them lives in the actual PR but worth flagging now.

1. **Strategy 0 rebalance frequency: quarterly or monthly?** Quarterly matches HSI's official cadence and is the lower-turnover choice (lower cost drag in the benchmark — important methodologically). Monthly is more common in academic factor research and gives the engine more rebalances to exercise. Recommendation: **quarterly** (default), parameterizable. Confirm or override.
2. **Equal-weighted vs cap-weighted benchmark?** True HSI is cap-weighted. We don't have market caps in v1 (would require additional yfinance / Bloomberg ingestion). Two paths: (a) **equal-weighted** + document deviation; (b) ingest market caps via yfinance `Ticker.info['marketCap']` as a separate quarterly ingestion task. (a) is faster; (b) is more faithful. Recommendation: **(a)** for Phase 2, schedule (b) for Phase 5 with Bloomberg. Confirm or override.
3. **Initial capital default?** Architecture doesn't pin a number. Common defaults: 1M HKD, 10M HKD, 100M HKD (institutional). Larger initial capital makes the slippage curve more punishing (proportional to notional / volume). Recommendation: **1,000,000 HKD** as the user-facing default; configurable. Confirm.
4. **`^HSI` ingestion for sanity check.** yfinance often accepts `^HSI` for the HSI price index. If it works, ingest it; if not, sanity-check against public sources manually. Recommendation: attempt the ingest on Day 22; document the result either way.

---

## Anti-procrastination notes

- **Phase 2 is the most code-dense phase so far** (~1500 LOC of code + tests). 2-Day Rule applies. If stuck on the engine for >2 days, stop and triage.
- **Don't over-engineer the engine.** v1 has one execution model (same-day close + one-day lag). Don't pre-build options for alternative timings.
- **Don't optimize prematurely.** A naive `for` loop over rebalance dates is fine for v1. We're not running thousands of backtests per second.
- **Build vertically, not horizontally.** Day 15 → 16 → ... → 22, each PR is mergeable and has working tests. Don't write Engine before Portfolio; don't write Strategy 0 before Strategy ABC. Each day's PR uses what the previous day built.

---

## What Phase 3 will need on Day 23

You don't need to build any of this in Phase 2, but knowing it's coming:

- Feature engineering (10 features × 4 families per ARCHITECTURE §4.2)
- Feature registry pattern
- Strategy 1 (multi-factor cross-sectional, sector-neutral, long-only) per §4.4
- Full FastAPI surface (per §5.2 — endpoint catalog)
- RQ worker for async backtest execution
- Frontend pages and 8 chart components per §6.6
- **End of Phase 3 = v1 MVP**, the original ship target

Don't pre-build any of this in Phase 2.
