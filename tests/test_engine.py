"""`BacktestEngine` integration tests against a synthetic in-memory DataSource.

Day 18 covers the happy path: a trivial buy-and-hold strategy across a
small synthetic price corpus, asserting per-day mark-to-market correctness,
trade execution timing, and snapshot-history completeness.

Day 19 will add edge cases (multi-rebalance cash flow, missing prices,
audit-wrapper fire on a leaky strategy).
"""

from __future__ import annotations

import datetime as dt
from typing import cast

import pandas as pd
import pytest

from azureus.backtesting import engine as engine_module
from azureus.backtesting.cost_model import HKCostModel
from azureus.backtesting.engine import BacktestConfig, BacktestEngine
from azureus.backtesting.results import BacktestResult
from azureus.data.sources.auditing import LookaheadError
from azureus.data.sources.base import DataSource
from azureus.strategies.base import StrategyContext


def _latest_holdings(result: BacktestResult) -> pd.DataFrame:
    """Holdings rows for the final equity-curve date."""
    if result.holdings.empty:
        return result.holdings
    final_date = result.equity_curve["date"].iloc[-1]
    return result.holdings[result.holdings["date"] == final_date]


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


class ScheduledWeightsStrategy:
    """Test strategy: return explicit target weights on configured rebalance dates."""

    def __init__(self, schedule: dict[dt.date, dict[str, float]]) -> None:
        ordered = sorted(schedule.items())
        self._rebalance_dates = [d for d, _target in ordered]
        self._targets = [target for _d, target in ordered]
        self._target_index = 0

    def rebalance_dates(self, start: dt.date, end: dt.date) -> list[dt.date]:
        return [d for d in self._rebalance_dates if start <= d <= end]

    def target_weights(self, ctx: StrategyContext) -> dict[str, float]:
        target = self._targets[self._target_index]
        self._target_index += 1
        return target


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
    result = engine.run()
    assert len(result.equity_curve) > 0
    assert result.equity_curve["date"].iloc[0] >= start
    assert result.equity_curve["date"].iloc[-1] <= end


def test_engine_executes_single_rebalance_and_holds(buy_and_hold_setup) -> None:
    ds, start, end = buy_and_hold_setup
    strategy = BuyAndHoldOnce(ticker="0700.HK", first_rebalance=start)
    engine = BacktestEngine(
        strategy=strategy,
        data_source=ds,
        cost_model=HKCostModel(),
        config=BacktestConfig(start=start, end=end, initial_capital=1_000_000.0),
    )
    result = engine.run()
    final_holdings = _latest_holdings(result)

    # After the rebalance we should hold 0700.HK and very little cash
    # (the residual is HK trading costs).
    assert set(final_holdings["ticker"]) == {"0700.HK"}
    assert float(result.summary["final_cash"]) < float(result.summary["final_value"]) * 0.05
    # Final share count should be ~initial_cash / fill_price_at_rebalance.
    fill_close = ds.get_prices(["0700.HK"], start, start, fields=("close",)).iloc[0]["close"]
    expected_shares = 1_000_000.0 / float(fill_close)
    actual_shares = float(final_holdings.iloc[0]["shares"])
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
    result = engine.run()

    initial = 1_000_000.0
    final = float(result.summary["final_value"])
    # Linear drift of $1/day on a base of $400 over the simulation window.
    # The engine's actual sim_days come from trading_days_between, so we
    # don't know exactly how many bars; assert "grew meaningfully" instead.
    assert final > initial * 1.01  # > 1% growth
    # Costs nibble at the return: should be a hair below the pre-cost figure.
    days_held = len(result.equity_curve)
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
    result = engine.run()

    # Each snapshot is one trading day; dates strictly increasing.
    dates = list(result.equity_curve["date"])
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
    result = engine.run()

    # If costs were zero, day-1 total value would equal initial capital exactly
    # (we'd just be holding stock equal to the cash we spent).
    # With costs, day-1 total value is slightly less.
    day_one = result.equity_curve.iloc[0]
    assert day_one["total_value"] < 1_000_000.0
    assert day_one["total_value"] > 1_000_000.0 * 0.99  # < 1% in costs


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
    result = engine.run()

    assert result.summary["final_cash"] == 1_000_000.0
    assert result.holdings.empty
    assert all(result.equity_curve["total_value"] == 1_000_000.0)


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
    result = engine.run()
    assert result.summary["final_cash"] == 1_000_000.0
    assert result.equity_curve.empty


# ---- Day 19 edge cases ---------------------------------------------------


def test_multi_rebalance_updates_holdings_and_costs_cash_flow() -> None:
    """Two rebalances should sell the old target, buy the new one, and pay costs."""
    first_rebalance = dt.date(2024, 1, 2)
    second_rebalance = dt.date(2024, 1, 10)
    start = first_rebalance
    end = dt.date(2024, 1, 12)
    prices = pd.concat(
        [
            _build_synthetic_prices("0700.HK", dt.date(2023, 11, 1), 100, 400.0, 1.0, 10_000_000),
            _build_synthetic_prices("0005.HK", dt.date(2023, 11, 1), 100, 60.0, 0.1, 10_000_000),
        ],
        ignore_index=True,
    )
    ds = SyntheticDataSource(prices=prices, universe=["0700.HK", "0005.HK"])
    strategy = ScheduledWeightsStrategy(
        {
            first_rebalance: {"0700.HK": 0.50},
            second_rebalance: {"0005.HK": 0.50},
        }
    )
    engine = BacktestEngine(
        strategy=strategy,
        data_source=ds,
        cost_model=HKCostModel(slippage_alpha=0.0),
        config=BacktestConfig(start=start, end=end, initial_capital=1_000_000.0),
    )
    frictionless_engine = BacktestEngine(
        strategy=ScheduledWeightsStrategy(
            {
                first_rebalance: {"0700.HK": 0.50},
                second_rebalance: {"0005.HK": 0.50},
            }
        ),
        data_source=ds,
        cost_model=HKCostModel(
            commission_bps=0.0,
            stamp_duty_bps=0.0,
            sfc_levy_bps=0.0,
            hkex_fee_bps=0.0,
            ccass_fee_bps=0.0,
            slippage_alpha=0.0,
        ),
        config=BacktestConfig(start=start, end=end, initial_capital=1_000_000.0),
    )

    result = engine.run()
    frictionless_result = frictionless_engine.run()

    assert set(_latest_holdings(result)["ticker"]) == {"0005.HK"}
    assert float(result.summary["final_value"]) < float(frictionless_result.summary["final_value"])
    assert float(result.summary["final_cash"]) < float(frictionless_result.summary["final_cash"])


def test_missing_target_fill_price_logs_and_skips_untradeable_ticker(
    buy_and_hold_setup,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ds, start, end = buy_and_hold_setup
    warnings: list[str] = []

    def _capture_warning(message: str, *args: object, **kwargs: object) -> None:
        _ = kwargs
        warnings.append(message % args)

    monkeypatch.setattr(engine_module.logger, "warning", _capture_warning)
    strategy = ScheduledWeightsStrategy(
        {
            start: {
                "0700.HK": 0.50,
                "MISSING.HK": 0.50,
            }
        }
    )
    engine = BacktestEngine(
        strategy=strategy,
        data_source=ds,
        cost_model=HKCostModel(),
        config=BacktestConfig(start=start, end=end, initial_capital=1_000_000.0),
    )

    result = engine.run()

    assert set(_latest_holdings(result)["ticker"]) == {"0700.HK"}
    assert any("MISSING.HK" in warning for warning in warnings)
    assert any("missing close price" in warning for warning in warnings)


def test_leaky_strategy_fails_mid_run_when_using_audited_source(buy_and_hold_setup) -> None:
    """A strategy that reads future fundamentals should trip the audit wrapper."""

    class LeakyFundamentalsDataSource(SyntheticDataSource):
        def get_fundamentals(
            self,
            tickers: list[str],
            as_of_date: dt.date,
            metrics: list[str],
        ) -> pd.DataFrame:
            return pd.DataFrame(
                {
                    "ticker": [tickers[0]],
                    "metric": [metrics[0]],
                    "period_end": [dt.date(2024, 3, 31)],
                    "reported_date": [as_of_date + dt.timedelta(days=30)],
                    "value": [1.0],
                }
            )

    class FundamentalsReadingStrategy(BuyAndHoldOnce):
        def __init__(self, ticker: str, first_rebalance: dt.date) -> None:
            super().__init__(ticker=ticker, first_rebalance=first_rebalance)
            self.data_source: DataSource | None = None

        def target_weights(self, ctx: StrategyContext) -> dict[str, float]:
            assert self.data_source is not None
            self.data_source.get_fundamentals(
                tickers=[self._ticker],
                as_of_date=ctx.as_of_date,
                metrics=["earnings"],
            )
            return super().target_weights(ctx)

    ds, start, end = buy_and_hold_setup
    leaky_ds = LeakyFundamentalsDataSource(prices=ds._prices, universe=["0700.HK"])
    strategy = FundamentalsReadingStrategy(ticker="0700.HK", first_rebalance=start)
    engine = BacktestEngine(
        strategy=strategy,
        data_source=leaky_ds,
        cost_model=HKCostModel(),
        config=BacktestConfig(start=start, end=end, initial_capital=1_000_000.0),
    )
    strategy.data_source = cast(DataSource, engine._data_source)

    with pytest.raises(LookaheadError, match="reported_date > as_of_date"):
        engine.run()


def test_engine_injects_audited_source_into_strategy_data(buy_and_hold_setup) -> None:
    """Strategies using `self.data` must read through the audit wrapper."""

    class LeakyFundamentalsDataSource(SyntheticDataSource):
        def get_fundamentals(
            self,
            tickers: list[str],
            as_of_date: dt.date,
            metrics: list[str],
        ) -> pd.DataFrame:
            return pd.DataFrame(
                {
                    "ticker": [tickers[0]],
                    "metric": [metrics[0]],
                    "period_end": [dt.date(2024, 3, 31)],
                    "reported_date": [as_of_date + dt.timedelta(days=30)],
                    "value": [1.0],
                }
            )

    class SelfDataReadingStrategy(BuyAndHoldOnce):
        def __init__(self, ticker: str, first_rebalance: dt.date) -> None:
            super().__init__(ticker=ticker, first_rebalance=first_rebalance)
            self.data: DataSource | None = None

        def target_weights(self, ctx: StrategyContext) -> dict[str, float]:
            assert self.data is not None
            self.data.get_fundamentals(
                tickers=[self._ticker],
                as_of_date=ctx.as_of_date,
                metrics=["earnings"],
            )
            return super().target_weights(ctx)

    ds, start, end = buy_and_hold_setup
    leaky_ds = LeakyFundamentalsDataSource(prices=ds._prices, universe=["0700.HK"])
    strategy = SelfDataReadingStrategy(ticker="0700.HK", first_rebalance=start)
    engine = BacktestEngine(
        strategy=strategy,
        data_source=leaky_ds,
        cost_model=HKCostModel(),
        config=BacktestConfig(start=start, end=end, initial_capital=1_000_000.0),
    )

    assert strategy.data is engine._data_source
    with pytest.raises(LookaheadError, match="reported_date > as_of_date"):
        engine.run()


def test_missing_held_ticker_price_surfaces_portfolio_key_error(buy_and_hold_setup) -> None:
    """Once a ticker is held, missing mark-to-market data is a hard engine failure."""

    class MissingHeldPriceDataSource(SyntheticDataSource):
        def __init__(
            self,
            prices: pd.DataFrame,
            universe: list[str],
            missing_date: dt.date,
        ) -> None:
            super().__init__(prices, universe)
            self._missing_date = missing_date

        def get_prices(
            self,
            tickers: list[str],
            start: dt.date,
            end: dt.date,
            fields: tuple[str, ...] = ("close",),
        ) -> pd.DataFrame:
            if fields == ("close",) and start == end == self._missing_date:
                return pd.DataFrame(columns=["date", "ticker", "close"])
            return super().get_prices(tickers, start, end, fields)

    ds, start, end = buy_and_hold_setup
    missing_date = dt.date(2024, 1, 3)
    broken_ds = MissingHeldPriceDataSource(ds._prices, ["0700.HK"], missing_date)
    strategy = BuyAndHoldOnce(ticker="0700.HK", first_rebalance=start)
    engine = BacktestEngine(
        strategy=strategy,
        data_source=broken_ds,
        cost_model=HKCostModel(),
        config=BacktestConfig(start=start, end=end, initial_capital=1_000_000.0),
    )

    with pytest.raises(KeyError, match="missing price for held ticker"):
        engine.run()


def test_insufficient_mdv_history_surfaces_value_error() -> None:
    """The engine should fail loud when slippage cannot be priced."""
    prices = pd.DataFrame(
        {
            "date": pd.to_datetime(["2023-12-28", "2023-12-29", "2024-01-02"]),
            "ticker": ["0700.HK", "0700.HK", "0700.HK"],
            "close": [400.0, 401.0, 402.0],
            "volume": [1_000_000, 1_000_000, 1_000_000],
        }
    )
    ds = SyntheticDataSource(prices=prices, universe=["0700.HK"])
    start = dt.date(2024, 1, 2)
    strategy = BuyAndHoldOnce(ticker="0700.HK", first_rebalance=start)
    engine = BacktestEngine(
        strategy=strategy,
        data_source=ds,
        cost_model=HKCostModel(),
        config=BacktestConfig(start=start, end=start, initial_capital=1_000_000.0),
    )

    with pytest.raises(ValueError, match="insufficient volume history"):
        engine.run()
