"""Tests for Strategy 0: equal-weighted HSI benchmark."""

from __future__ import annotations

import datetime as dt

import pandas as pd
import pytest

from azureus.strategies.base import StrategyContext
from azureus.strategies.benchmark import BenchmarkParams, EqualWeightedHSIBenchmark
from azureus.strategies.registry import get_strategy, list_strategies
from azureus.utils.dates import is_trading_day, roll_to_trading_day


class BenchmarkDataSource:
    """Minimal DataSource fake for benchmark strategy tests."""

    provider_name = "benchmark-test"

    def __init__(self, prices: pd.DataFrame, universe: list[str]) -> None:
        self._prices = prices
        self._universe = universe

    def get_universe(self, index_id: str, as_of_date: dt.date) -> list[str]:
        return list(self._universe)

    def get_universe_history(self, index_id: str, start: dt.date, end: dt.date) -> pd.DataFrame:
        return pd.DataFrame()

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
        return self._prices.loc[mask, ["date", "ticker", *fields]].copy()

    def get_fundamentals(
        self,
        tickers: list[str],
        as_of_date: dt.date,
        metrics: list[str],
    ) -> pd.DataFrame:
        return pd.DataFrame()

    def get_fundamentals_history(
        self,
        tickers: list[str],
        start: dt.date,
        end: dt.date,
        metrics: list[str],
    ) -> pd.DataFrame:
        return pd.DataFrame()

    def get_macro(self, series_ids: list[str], start: dt.date, end: dt.date) -> pd.DataFrame:
        return pd.DataFrame()

    def list_available_tickers(self, index_id: str | None = None) -> list[str]:
        return list(self._universe)

    def list_available_metrics(self) -> list[str]:
        return []


@pytest.fixture
def benchmark_source() -> BenchmarkDataSource:
    rows: list[dict[str, object]] = []
    for day in pd.bdate_range(end="2023-12-29", periods=6):
        rows.append({"date": day, "ticker": "0700.HK", "close": 400.0, "volume": 1_000_000})
        rows.append({"date": day, "ticker": "0005.HK", "close": 60.0, "volume": 1_000_000})
    prices = pd.DataFrame(rows)
    return BenchmarkDataSource(prices=prices, universe=["0700.HK", "0005.HK", "0011.HK"])


def test_benchmark_rebalance_dates_are_quarterly_trading_days(
    benchmark_source: BenchmarkDataSource,
) -> None:
    strategy = EqualWeightedHSIBenchmark(BenchmarkParams(), benchmark_source)

    dates = strategy.rebalance_dates(dt.date(2024, 1, 1), dt.date(2024, 10, 31))

    assert dates == [
        roll_to_trading_day(dt.date(2024, 1, 1)),
        roll_to_trading_day(dt.date(2024, 4, 1)),
        roll_to_trading_day(dt.date(2024, 7, 1)),
        roll_to_trading_day(dt.date(2024, 10, 1)),
    ]
    assert all(is_trading_day(d) for d in dates)


def test_benchmark_target_weights_sum_to_one(benchmark_source: BenchmarkDataSource) -> None:
    strategy = EqualWeightedHSIBenchmark(BenchmarkParams(), benchmark_source)
    ctx = StrategyContext(
        as_of_date=dt.date(2023, 12, 29),
        universe=["0700.HK", "0005.HK"],
        portfolio_value=1_000_000.0,
        current_weights={},
    )

    weights = strategy.target_weights(ctx)

    assert set(weights) == {"0700.HK", "0005.HK"}
    assert sum(weights.values()) == pytest.approx(1.0)
    assert weights["0700.HK"] == pytest.approx(0.5)
    assert weights["0005.HK"] == pytest.approx(0.5)


def test_benchmark_excludes_universe_member_with_no_price_data(
    benchmark_source: BenchmarkDataSource,
) -> None:
    strategy = EqualWeightedHSIBenchmark(BenchmarkParams(), benchmark_source)
    ctx = StrategyContext(
        as_of_date=dt.date(2023, 12, 29),
        universe=["0700.HK", "0005.HK", "0011.HK"],
        portfolio_value=1_000_000.0,
        current_weights={},
    )

    weights = strategy.target_weights(ctx)

    assert set(weights) == {"0700.HK", "0005.HK"}
    assert "0011.HK" not in weights


def test_benchmark_freezes_currently_held_untradeable_member(
    benchmark_source: BenchmarkDataSource,
) -> None:
    strategy = EqualWeightedHSIBenchmark(BenchmarkParams(), benchmark_source)
    ctx = StrategyContext(
        as_of_date=dt.date(2023, 12, 29),
        universe=["0700.HK", "0005.HK", "0011.HK"],
        portfolio_value=1_000_000.0,
        current_weights={"0011.HK": 0.10},
    )

    weights = strategy.target_weights(ctx)

    assert weights["0011.HK"] == 0.10
    assert weights["0700.HK"] == pytest.approx(0.45)
    assert weights["0005.HK"] == pytest.approx(0.45)
    assert sum(weights.values()) == pytest.approx(1.0)


def test_benchmark_strategy_is_registered() -> None:
    assert get_strategy(EqualWeightedHSIBenchmark.id) is EqualWeightedHSIBenchmark
    assert EqualWeightedHSIBenchmark in list_strategies()
