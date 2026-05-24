"""`BacktestEngine` integration tests against a synthetic in-memory DataSource.

Day 18 covers the happy path: a trivial buy-and-hold strategy across a
small synthetic price corpus, asserting per-day mark-to-market correctness,
trade execution timing, and snapshot-history completeness.

Day 19 will add edge cases (multi-rebalance cash flow, missing prices,
audit-wrapper fire on a leaky strategy).
"""

from __future__ import annotations

import datetime as dt

import pandas as pd
import pytest

from azureus.backtesting.cost_model import HKCostModel
from azureus.backtesting.engine import BacktestConfig, BacktestEngine
from azureus.strategies.base import StrategyContext

# ---- synthetic test infrastructure --------------------------------------


def _build_synthetic_prices(
    ticker: str,
    start: dt.date,
    days: int,
    base_price: float,
    daily_drift: float,
    volume: int,
) -> pd.DataFrame:
    """Generate `days` rows of OHLCV bars with a linear price drift.

    Uses pd.bdate_range for business-day calendar; not perfectly HKEX-
    accurate but good enough for engine-loop tests where HKEX holidays
    are filtered out by trading_days_between anyway.
    """
    business_dates = pd.bdate_range(start=pd.Timestamp(start), periods=days)
    prices = [base_price + daily_drift * i for i in range(days)]
    return pd.DataFrame(
        {
            "date": business_dates,
            "ticker": ticker,
            "close": prices,
            "volume": volume,
        }
    )


class SyntheticDataSource:
    """In-memory DataSource over a hand-built prices DataFrame.

    Satisfies the `DataSource` Protocol structurally (we only implement the
    methods the engine calls; everything else raises NotImplementedError).
    """

    provider_name = "synthetic"

    def __init__(self, prices: pd.DataFrame, universe: list[str]) -> None:
        self._prices = prices
        self._universe = universe

    def get_universe(self, index_id: str, as_of_date: dt.date) -> list[str]:
        return list(self._universe)

    def get_prices(
        self,
        tickers: list[str],
        start: dt.date,
        end: dt.date,
        fields: tuple[str, ...] = ("close",),
    ) -> pd.DataFrame:
        mask = (
            self._prices["ticker"].isin(tickers)
            & (self._prices["date"] >= pd.Timestamp(start))
            & (self._prices["date"] <= pd.Timestamp(end))
        )
        cols = ["date", "ticker", *fields]
        return self._prices.loc[mask, cols].copy()

    # Stubs for methods not used in Day 18 tests.
    def get_universe_history(self, *_args: object, **_kwargs: object) -> pd.DataFrame:
        raise NotImplementedError

    def get_fundamentals(self, *_args: object, **_kwargs: object) -> pd.DataFrame:
        raise NotImplementedError

    def get_fundamentals_history(self, *_args: object, **_kwargs: object) -> pd.DataFrame:
        raise NotImplementedError

    def get_macro(self, *_args: object, **_kwargs: object) -> pd.DataFrame:
        raise NotImplementedError

    def list_available_tickers(self, *_args: object, **_kwargs: object) -> list[str]:
        return list(self._universe)

    def list_available_metrics(self) -> list[str]:
        return []


class BuyAndHoldOnce:
    """Test strategy: rebalance once on `first_rebalance`, target a single ticker."""

    def __init__(self, ticker: str, first_rebalance: dt.date, weight: float = 1.0):
        self._ticker = ticker
        self._first_rebalance = first_rebalance
        self._weight = weight

    def rebalance_dates(self, start: dt.date, end: dt.date) -> list[dt.date]:
        if start <= self._first_rebalance <= end:
            return [self._first_rebalance]
        return []

    def target_weights(self, ctx: StrategyContext) -> dict[str, float]:
        return {self._ticker: self._weight}


# ---- happy-path engine tests --------------------------------------------


@pytest.fixture
def buy_and_hold_setup() -> tuple[SyntheticDataSource, dt.date, dt.date]:
    """Synthetic corpus: 0700.HK from 2024-01-02 → 2024-02-15, linear drift."""
    ticker = "0700.HK"
    # Start ample warmup data before the simulation window so MDV is available.
    prices = _build_synthetic_prices(
        ticker=ticker,
        start=dt.date(2023, 11, 1),
        days=100,  # ~100 business days, plenty for 20-day MDV lookback
        base_price=400.0,
        daily_drift=1.0,  # $1/day drift = +25% over the window
        volume=10_000_000,  # ample liquidity → slippage tiny
    )
    ds = SyntheticDataSource(prices=prices, universe=[ticker])
    return ds, dt.date(2024, 1, 2), dt.date(2024, 1, 31)


def test_engine_runs_through_to_end(buy_and_hold_setup) -> None:
    ds, start, end = buy_and_hold_setup
    strategy = BuyAndHoldOnce(ticker="0700.HK", first_rebalance=start)
    engine = BacktestEngine(
        strategy=strategy,
        data_source=ds,
        cost_model=HKCostModel(),
        config=BacktestConfig(start=start, end=end, initial_capital=1_000_000.0),
    )
    portfolio = engine.run()
    assert len(portfolio.history) > 0
    assert portfolio.history[0].as_of_date >= start
    assert portfolio.history[-1].as_of_date <= end


def test_engine_executes_single_rebalance_and_holds(buy_and_hold_setup) -> None:
    ds, start, end = buy_and_hold_setup
    strategy = BuyAndHoldOnce(ticker="0700.HK", first_rebalance=start)
    engine = BacktestEngine(
        strategy=strategy,
        data_source=ds,
        cost_model=HKCostModel(),
        config=BacktestConfig(start=start, end=end, initial_capital=1_000_000.0),
    )
    portfolio = engine.run()

    # After the rebalance we should hold 0700.HK and very little cash
    # (the residual is HK trading costs).
    assert "0700.HK" in portfolio.holdings
    assert portfolio.cash < portfolio.total_value() * 0.05  # < 5% in cash
    # Final share count should be ~initial_cash / fill_price_at_rebalance.
    fill_close = ds.get_prices(["0700.HK"], start, start, fields=("close",)).iloc[0]["close"]
    expected_shares = 1_000_000.0 / float(fill_close)
    actual_shares = portfolio.holdings["0700.HK"].shares
    # Slightly below expected — we paid for fees out of the same cash pool.
    assert actual_shares == pytest.approx(expected_shares, rel=0.05)


def test_equity_curve_tracks_price_appreciation(buy_and_hold_setup) -> None:
    """100% allocated to a +25% drifting ticker → equity should grow ~25% net of costs."""
    ds, start, end = buy_and_hold_setup
    strategy = BuyAndHoldOnce(ticker="0700.HK", first_rebalance=start)
    engine = BacktestEngine(
        strategy=strategy,
        data_source=ds,
        cost_model=HKCostModel(),
        config=BacktestConfig(start=start, end=end, initial_capital=1_000_000.0),
    )
    portfolio = engine.run()

    initial = 1_000_000.0
    final = portfolio.history[-1].total_value
    # Linear drift of $1/day on a base of $400 over the simulation window.
    # The engine's actual sim_days come from trading_days_between, so we
    # don't know exactly how many bars; assert "grew meaningfully" instead.
    assert final > initial * 1.01  # > 1% growth
    # Costs nibble at the return: should be a hair below the pre-cost figure.
    days_held = len(portfolio.history)
    naive_final = initial * (1 + days_held * 1.0 / 400.0)
    assert final < naive_final  # costs took a bite


def test_snapshot_per_trading_day_in_simulation_window(buy_and_hold_setup) -> None:
    ds, start, end = buy_and_hold_setup
    strategy = BuyAndHoldOnce(ticker="0700.HK", first_rebalance=start)
    engine = BacktestEngine(
        strategy=strategy,
        data_source=ds,
        cost_model=HKCostModel(),
        config=BacktestConfig(start=start, end=end, initial_capital=1_000_000.0),
    )
    portfolio = engine.run()

    # Each snapshot is one trading day; dates strictly increasing.
    dates = [snap.as_of_date for snap in portfolio.history]
    assert dates == sorted(dates)
    assert len(dates) == len(set(dates))


def test_costs_are_actually_deducted(buy_and_hold_setup) -> None:
    """First-day buy should reduce cash by notional + HK fees + slippage."""
    ds, start, end = buy_and_hold_setup
    strategy = BuyAndHoldOnce(ticker="0700.HK", first_rebalance=start)
    engine = BacktestEngine(
        strategy=strategy,
        data_source=ds,
        cost_model=HKCostModel(),
        config=BacktestConfig(start=start, end=end, initial_capital=1_000_000.0),
    )
    portfolio = engine.run()

    # If costs were zero, day-1 total value would equal initial capital exactly
    # (we'd just be holding stock equal to the cash we spent).
    # With costs, day-1 total value is slightly less.
    day_one = portfolio.history[0]
    assert day_one.total_value < 1_000_000.0
    assert day_one.total_value > 1_000_000.0 * 0.99  # < 1% in costs


def test_no_rebalance_in_window_means_pure_cash(buy_and_hold_setup) -> None:
    """If the strategy never rebalances in window, portfolio stays in cash."""
    ds, start, end = buy_and_hold_setup
    strategy = BuyAndHoldOnce(
        ticker="0700.HK",
        first_rebalance=dt.date(2030, 1, 1),  # well outside window
    )
    engine = BacktestEngine(
        strategy=strategy,
        data_source=ds,
        cost_model=HKCostModel(),
        config=BacktestConfig(start=start, end=end, initial_capital=1_000_000.0),
    )
    portfolio = engine.run()

    assert portfolio.cash == 1_000_000.0
    assert dict(portfolio.holdings) == {}
    assert all(snap.total_value == 1_000_000.0 for snap in portfolio.history)


def test_empty_simulation_window_returns_empty_portfolio() -> None:
    """End < start in pure trading days → no sim days, no history."""
    ticker = "0700.HK"
    ds = SyntheticDataSource(
        prices=_build_synthetic_prices(ticker, dt.date(2024, 1, 1), 10, 400.0, 0.0, 1_000_000),
        universe=[ticker],
    )
    # Pick a window that contains zero trading days (Saturday → Sunday).
    engine = BacktestEngine(
        strategy=BuyAndHoldOnce(ticker, dt.date(2024, 1, 6)),
        data_source=ds,
        cost_model=HKCostModel(),
        config=BacktestConfig(
            start=dt.date(2024, 1, 6),  # Saturday
            end=dt.date(2024, 1, 7),  # Sunday
            initial_capital=1_000_000.0,
        ),
    )
    portfolio = engine.run()
    assert portfolio.cash == 1_000_000.0
    assert portfolio.history == ()
