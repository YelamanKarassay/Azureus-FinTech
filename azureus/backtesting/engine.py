"""`BacktestEngine` — the simulation loop driving Portfolio + CostModel.

Per ARCHITECTURE §4.6 the engine is built from scratch (not `vectorbt` /
`backtrader` / `zipline`). HK cross-sectional + PIT-aware factor backtests
don't fit those libraries cleanly — they're per-asset time-series tools.

Per-simulation-day algorithm:

1. **Mark to market** all currently-held positions at today's close.
2. **If rebalance day:**
   a. Build `StrategyContext` with `as_of_date = previous_trading_day(D)`
      (one-day signal lag — strategy sees data through D-1).
   b. Ask the strategy for `target_weights`.
   c. Diff target vs current holdings → `Trade` objects sized at today's
      close prices (same-day-close execution).
   d. Each trade → `ExecutedTrade` via the cost model, with rolling-20-
      day-median volume looked up for slippage.
   e. Apply each ExecutedTrade to the Portfolio.
3. **Snapshot** end-of-day state for the equity curve.

PIT enforcement: the engine auto-wraps the supplied `DataSource` in
`AuditingDataSource` by default. A leaky strategy fails loud mid-run
with `LookaheadError`. Override with `BacktestConfig.audit=False` only
if profiling shows the audit is a hot-path bottleneck (it isn't, at
our backtest cadence).

The engine returns a `BacktestResult`: daily equity curve, holdings,
executed trades, and summary analytics.
"""

from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass

from azureus.backtesting.cost_model import HKCostModel
from azureus.backtesting.portfolio import Portfolio
from azureus.backtesting.results import BacktestResult
from azureus.backtesting.value_objects import ExecutedTrade, Trade
from azureus.data.sources.auditing import AuditingDataSource
from azureus.data.sources.base import DataSource
from azureus.strategies.base import Strategy, StrategyContext
from azureus.utils.dates import (
    previous_trading_day,
    roll_to_trading_day,
    trading_days_between,
)

logger = logging.getLogger(__name__)

# How far back (calendar days) to look when computing the rolling median
# of daily volume. ~30 calendar days yields ~20 trading days; the engine
# requires at least 5 observed days before it will price slippage.
_MDV_LOOKBACK_CALENDAR_DAYS = 45
_MDV_MIN_OBSERVATIONS = 5
# Engine never re-orders trades at the same notional value — at our HK
# universe scale (~70 tickers, quarterly rebalances) this is fine.
_DEFAULT_UNIVERSE_ID = "HSI"


@dataclass(frozen=True)
class BacktestConfig:
    """Engine configuration. Immutable for the lifetime of a run."""

    start: dt.date
    end: dt.date
    initial_capital: float = 1_000_000.0
    universe_id: str = _DEFAULT_UNIVERSE_ID
    audit: bool = True


class BacktestEngine:
    """Drives a `Strategy` through `Portfolio` over time using `HKCostModel`.

    Constructor takes everything the simulation needs; `run()` does the
    work and returns the populated Portfolio. The engine caches per-
    ticker MDV per simulation date so a long backtest doesn't re-fetch
    volume history for every trade.
    """

    def __init__(
        self,
        strategy: Strategy,
        data_source: DataSource,
        cost_model: HKCostModel,
        config: BacktestConfig,
    ) -> None:
        self._strategy = strategy
        self._cost_model = cost_model
        self._config = config
        self._data_source: DataSource = (
            AuditingDataSource(data_source) if config.audit else data_source
        )
        # Strategies read market and PIT data through `self.data`; make the
        # audited source the one they see inside `target_weights`.
        self._strategy.data = self._data_source
        # MDV cache keyed by (ticker, sim_date). Cheap memory; engine
        # instances are short-lived (one per backtest).
        self._mdv_cache: dict[tuple[str, dt.date], float] = {}

    # ---- public entry point ---------------------------------------------

    def run(self) -> BacktestResult:
        sim_days = trading_days_between(self._config.start, self._config.end)
        portfolio = Portfolio(initial_cash=self._config.initial_capital)
        executed_trades: list[ExecutedTrade] = []
        if not sim_days:
            logger.warning(
                "no HKEX trading days in [%s, %s] — empty backtest",
                self._config.start,
                self._config.end,
            )
            return BacktestResult.from_portfolio(portfolio, executed_trades)

        rebalance_days = self._compute_rebalance_days(self._config.start, self._config.end)

        for sim_date in sim_days:
            # Step 1: mark currently-held positions at today's close.
            if portfolio.holdings:
                held_prices = self._fetch_close_prices(list(portfolio.holdings.keys()), sim_date)
                portfolio.mark_to_market(held_prices)

            # Step 2: if rebalance day, generate and execute trades.
            if sim_date in rebalance_days:
                executed_trades.extend(self._do_rebalance(portfolio, sim_date))

            # Step 3: record end-of-day snapshot.
            portfolio.record_snapshot(sim_date)

        return BacktestResult.from_portfolio(portfolio, executed_trades)

    # ---- internals ------------------------------------------------------

    def _compute_rebalance_days(
        self,
        start: dt.date,
        end: dt.date,
    ) -> set[dt.date]:
        """Strategy-supplied rebalance dates, normalised to trading days.

        Drops dates outside `[start, end]` and rolls non-trading days
        forward to the next session (per Day 15 calendar convention).
        """
        raw = self._strategy.rebalance_dates(start, end)
        result: set[dt.date] = set()
        for d in raw:
            if not (start <= d <= end):
                continue
            rolled = roll_to_trading_day(d)
            if start <= rolled <= end:
                result.add(rolled)
        return result

    def _do_rebalance(self, portfolio: Portfolio, sim_date: dt.date) -> list[ExecutedTrade]:
        """Run one rebalance: ask strategy → diff → execute → apply."""
        as_of = previous_trading_day(sim_date)
        ctx = StrategyContext(
            as_of_date=as_of,
            universe=self._data_source.get_universe(self._config.universe_id, as_of),
            portfolio_value=portfolio.total_value(),
            current_weights=dict(portfolio.weights()),
        )
        target_weights = self._strategy.target_weights(ctx)

        # All tickers we need fill prices for: target tickers (to buy/scale)
        # plus current holdings (to sell out).
        affected_tickers = set(target_weights.keys()) | set(portfolio.holdings.keys())
        if not affected_tickers:
            return []
        fill_prices = self._fetch_close_prices(list(affected_tickers), sim_date)
        missing_fill_tickers = sorted(affected_tickers - set(fill_prices))
        if missing_fill_tickers:
            logger.warning(
                "skipping %d ticker(s) with missing close price on %s: %s",
                len(missing_fill_tickers),
                sim_date,
                ", ".join(missing_fill_tickers),
            )

        trades = _diff_to_trades(target_weights, portfolio, fill_prices)
        executed_trades: list[ExecutedTrade] = []
        for trade in trades:
            mdv = self._get_median_daily_volume(trade.ticker, sim_date)
            fill_price = fill_prices[trade.ticker]
            executed = self._cost_model.execute(trade, fill_price, mdv, sim_date)
            portfolio.apply_executed_trade(executed)
            executed_trades.append(executed)
        return executed_trades

    def _fetch_close_prices(
        self,
        tickers: list[str],
        sim_date: dt.date,
    ) -> dict[str, float]:
        """Today's closes for `tickers`, keyed by ticker. Missing → omitted."""
        if not tickers:
            return {}
        df = self._data_source.get_prices(
            tickers=tickers,
            start=sim_date,
            end=sim_date,
            fields=("close",),
        )
        if df.empty:
            return {}
        return {str(row["ticker"]): float(row["close"]) for _, row in df.iterrows()}

    def _get_median_daily_volume(self, ticker: str, sim_date: dt.date) -> float:
        """Rolling-20-day median volume ending the trading day before `sim_date`.

        Cached per (ticker, sim_date). Raises ValueError if fewer than
        `_MDV_MIN_OBSERVATIONS` observed days are available — the cost
        model would otherwise silently mis-price slippage.
        """
        key = (ticker, sim_date)
        if key in self._mdv_cache:
            return self._mdv_cache[key]

        window_end = previous_trading_day(sim_date)
        window_start = sim_date - dt.timedelta(days=_MDV_LOOKBACK_CALENDAR_DAYS)
        df = self._data_source.get_prices(
            tickers=[ticker],
            start=window_start,
            end=window_end,
            fields=("volume",),
        )
        if df.empty or "volume" not in df.columns:
            raise ValueError(
                f"no volume data for {ticker} in [{window_start}, {window_end}] "
                "— cannot price slippage"
            )
        # Volume can be null on suspension days; drop them.
        volume = df["volume"].dropna()
        if len(volume) < _MDV_MIN_OBSERVATIONS:
            raise ValueError(
                f"insufficient volume history for {ticker} ending {window_end}: "
                f"{len(volume)} observed days < {_MDV_MIN_OBSERVATIONS} required"
            )
        mdv = float(volume.median())
        self._mdv_cache[key] = mdv
        return mdv


def _diff_to_trades(
    target_weights: dict[str, float],
    portfolio: Portfolio,
    fill_prices: dict[str, float],
) -> list[Trade]:
    """Build `Trade` list from current portfolio + target weights.

    For each ticker in (target ∪ current holdings), compute the share
    delta needed at today's fill price to reach the target weight. Skip
    tickers with no fill price (the engine treats those as untradeable
    today; Day 19 adds explicit warning logic).
    """
    portfolio_value = portfolio.total_value()
    current_holdings = portfolio.holdings

    affected = set(target_weights.keys()) | set(current_holdings.keys())
    trades: list[Trade] = []
    for ticker in sorted(affected):  # deterministic order for reproducibility
        if ticker not in fill_prices:
            continue
        fill_price = fill_prices[ticker]
        target_weight = target_weights.get(ticker, 0.0)
        target_notional = target_weight * portfolio_value
        target_shares = target_notional / fill_price if fill_price > 0 else 0.0

        current_shares = current_holdings[ticker].shares if ticker in current_holdings else 0.0
        delta_shares = target_shares - current_shares
        if delta_shares == 0.0:
            continue
        trades.append(Trade(ticker=ticker, shares=delta_shares, reference_price=fill_price))
    return trades
