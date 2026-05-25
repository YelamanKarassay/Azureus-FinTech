"""Golden regression test for Strategy 0 + BacktestEngine semantics."""

from __future__ import annotations

import datetime as dt

import pandas as pd
import pytest

from azureus.backtesting.cost_model import HKCostModel
from azureus.backtesting.engine import BacktestConfig, BacktestEngine
from azureus.strategies.benchmark import BenchmarkParams, EqualWeightedHSIBenchmark
from azureus.utils.dates import trading_days_between


class RegressionDataSource:
    """Deterministic two-ticker corpus for benchmark golden-output tests."""

    provider_name = "benchmark-regression"

    def __init__(self, prices: pd.DataFrame) -> None:
        self._prices = prices
        self._universe = ["0700.HK", "0005.HK"]

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


def _benchmark_regression_source() -> RegressionDataSource:
    rows: list[dict[str, object]] = []
    days = trading_days_between(dt.date(2023, 12, 1), dt.date(2024, 12, 31))
    for i, day in enumerate(days):
        rows.append(
            {
                "date": pd.Timestamp(day),
                "ticker": "0700.HK",
                "close": 100.0 + i * 0.05,
                "volume": 10_000_000,
            }
        )
        rows.append(
            {
                "date": pd.Timestamp(day),
                "ticker": "0005.HK",
                "close": 80.0 + i * 0.02,
                "volume": 10_000_000,
            }
        )
    return RegressionDataSource(pd.DataFrame(rows))


def test_equal_weight_benchmark_golden_output() -> None:
    data_source = _benchmark_regression_source()
    strategy = EqualWeightedHSIBenchmark(BenchmarkParams(), data_source)
    engine = BacktestEngine(
        strategy=strategy,
        data_source=data_source,
        cost_model=HKCostModel(slippage_alpha=0.0),
        config=BacktestConfig(
            start=dt.date(2024, 1, 2),
            end=dt.date(2024, 12, 31),
            initial_capital=1_000_000.0,
        ),
    )

    result = engine.run()

    assert result.summary["final_value"] == pytest.approx(1_090_505.663873663)
    assert result.summary["total_return"] == pytest.approx(0.09050566387366299)
    assert result.summary["annualized_return"] == pytest.approx(0.09281256505634516)
    assert result.summary["sharpe"] == pytest.approx(130.9278896155497)
    assert result.summary["max_drawdown"] == 0.0
    assert result.summary["total_trades"] == 8
    assert result.summary["total_costs"] == pytest.approx(314.82753524156834)
    assert len(result.equity_curve) == 246
