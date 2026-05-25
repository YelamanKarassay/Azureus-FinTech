"""Tests for Strategy 1: multi-factor v1."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import pandas as pd
import pytest

from azureus.data.sources.base import DataSource
from azureus.strategies.base import StrategyContext
from azureus.strategies.multi_factor_v1 import (
    MultiFactorV1Params,
    MultiFactorV1Strategy,
)
from azureus.strategies.registry import get_strategy, list_strategies


@dataclass
class FakeFeature:
    """Tiny feature implementation for strategy selection tests."""

    name: str
    family: str
    values: dict[str, float]
    description: str = "fake feature"
    requires_metrics: tuple[str, ...] = ()
    requires_lookback_days: int = 0

    def compute(
        self,
        data: DataSource,
        tickers: list[str],
        as_of_date: dt.date,
    ) -> pd.Series:
        _ = (data, as_of_date)
        series = pd.Series(
            {ticker: self.values[ticker] for ticker in tickers if ticker in self.values},
            dtype="float64",
        )
        series.name = self.name
        return series


class StrategyDataSource:
    """Minimal in-memory DataSource for Strategy 1 tests."""

    provider_name = "strategy-test"

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
        return self._prices.loc[mask, ["date", "provider", "ticker", *fields]].copy()

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


def _strategy_source(
    tickers: list[str],
    *,
    as_of_date: dt.date = dt.date(2025, 3, 31),
    illiquid: set[str] | None = None,
) -> StrategyDataSource:
    illiquid = illiquid or set()
    rows: list[dict[str, object]] = []
    for day in pd.bdate_range(end=pd.Timestamp(as_of_date), periods=8):
        for ticker in tickers:
            rows.append(
                {
                    "date": day,
                    "provider": "yfinance",
                    "ticker": ticker,
                    "close": 10.0,
                    "adjusted_close": 10.0,
                    "volume": 10 if ticker in illiquid else 200_000,
                }
            )
    return StrategyDataSource(prices=pd.DataFrame(rows), universe=tickers)


def _strategy_with_features(
    params: MultiFactorV1Params,
    data: StrategyDataSource,
    features: list[FakeFeature],
) -> MultiFactorV1Strategy:
    strategy = MultiFactorV1Strategy(params, data)
    strategy._features = features
    strategy._feature_families = {feature.name: feature.family for feature in features}
    return strategy


def _context(tickers: list[str], as_of_date: dt.date = dt.date(2025, 3, 31)) -> StrategyContext:
    return StrategyContext(
        as_of_date=as_of_date,
        universe=tickers,
        portfolio_value=1_000_000.0,
        current_weights={},
    )


def test_multi_factor_strategy_is_registered() -> None:
    assert get_strategy(MultiFactorV1Strategy.id) is MultiFactorV1Strategy
    assert MultiFactorV1Strategy in list_strategies()


def test_rebalance_dates_support_monthly_and_quarterly() -> None:
    data = _strategy_source(["T00.HK"])

    monthly = MultiFactorV1Strategy(MultiFactorV1Params(), data).rebalance_dates(
        dt.date(2024, 1, 1),
        dt.date(2024, 4, 30),
    )
    quarterly = MultiFactorV1Strategy(
        MultiFactorV1Params(rebalance_frequency="quarterly"),
        data,
    ).rebalance_dates(dt.date(2024, 1, 1), dt.date(2024, 4, 30))

    assert len(monthly) == 4
    assert len(quarterly) == 2


def test_target_weights_exclude_illiquid_and_missing_feature_tickers() -> None:
    tickers = [f"T{i:02d}.HK" for i in range(12)]
    data = _strategy_source(tickers, illiquid={"T10.HK"})
    values = {ticker: float(100 - i) for i, ticker in enumerate(tickers)}
    values.pop("T11.HK")
    strategy = _strategy_with_features(
        MultiFactorV1Params(
            n_long=10,
            sector_neutral=False,
            factor_weights={"value": 1.0},
            liquidity_threshold_usd=1_000_000.0,
        ),
        data,
        [FakeFeature(name="value_signal", family="value", values=values)],
    )

    weights = strategy.target_weights(_context(tickers))

    assert "T10.HK" not in weights
    assert "T11.HK" not in weights
    assert len(weights) == 10
    assert sum(weights.values()) == pytest.approx(1.0)


def test_sector_neutral_selection_uses_proportional_sector_slots() -> None:
    tickers = [f"T{i:02d}.HK" for i in range(12)]
    sector_map = {ticker: "Tech" if i < 8 else "Finance" for i, ticker in enumerate(tickers)}
    data = _strategy_source(tickers)
    # Raw Tech scores dominate. Sector-neutral selection should still keep
    # Finance representation proportional to candidate availability.
    values = {ticker: (100.0 - i if i < 8 else 10.0 - i) for i, ticker in enumerate(tickers)}
    strategy = _strategy_with_features(
        MultiFactorV1Params(
            n_long=10,
            sector_neutral=True,
            factor_weights={"value": 1.0},
            liquidity_threshold_usd=1_000_000.0,
            sector_map=sector_map,
        ),
        data,
        [FakeFeature(name="value_signal", family="value", values=values)],
    )

    weights = strategy.target_weights(_context(tickers))
    selected_sectors = [sector_map[ticker] for ticker in weights]

    assert selected_sectors.count("Tech") == 7
    assert selected_sectors.count("Finance") == 3
    assert sum(weights.values()) == pytest.approx(1.0)


def test_target_weights_are_deterministic_for_tied_scores() -> None:
    tickers = [f"T{i:02d}.HK" for i in range(12)]
    data = _strategy_source(tickers)
    values = dict.fromkeys(tickers, 1.0)
    strategy = _strategy_with_features(
        MultiFactorV1Params(
            n_long=10,
            sector_neutral=False,
            factor_weights={"value": 1.0},
            liquidity_threshold_usd=1_000_000.0,
        ),
        data,
        [FakeFeature(name="value_signal", family="value", values=values)],
    )

    first = strategy.target_weights(_context(tickers))
    second = strategy.target_weights(_context(tickers))

    assert first == second
    assert list(first) == tickers[:10]
    assert all(weight == pytest.approx(0.1) for weight in first.values())
