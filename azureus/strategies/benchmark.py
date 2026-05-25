"""Strategy 0: equal-weighted HSI benchmark.

This is an explicit Phase 2 compromise: true HSI is market-cap weighted,
but v1 does not yet ingest reliable historical market caps. The benchmark
therefore equal-weights available HSI members and documents the deviation.
"""

from __future__ import annotations

import datetime as dt
from typing import ClassVar, Literal, cast

import pandas as pd
from pydantic import Field

from azureus.strategies.base import Strategy, StrategyContext, StrategyParams
from azureus.utils.dates import roll_to_trading_day

_QUARTER_START_MONTHS = (1, 4, 7, 10)
_LIQUIDITY_LOOKBACK_DAYS = 45
_MIN_POSITIVE_VOLUME_OBSERVATIONS = 5


class BenchmarkParams(StrategyParams):
    """Parameters for the equal-weighted HSI benchmark."""

    universe_id: str = Field(default="HSI", min_length=1)
    rebalance_frequency: Literal["quarterly"] = "quarterly"


class EqualWeightedHSIBenchmark(Strategy):
    """Equal-weight all HSI members with available close data."""

    id: ClassVar[str] = "benchmark_equal_weight_hsi"
    name: ClassVar[str] = "Equal-Weighted HSI Benchmark"
    description: ClassVar[str] = (
        "Quarterly rebalanced, equal-weighted benchmark over available HSI members."
    )
    params_model: ClassVar[type[BenchmarkParams]] = BenchmarkParams

    @property
    def benchmark_params(self) -> BenchmarkParams:
        """Typed view of validated params."""
        return cast(BenchmarkParams, self.params)

    def rebalance_dates(self, start: dt.date, end: dt.date) -> list[dt.date]:
        """First HKEX trading day of each calendar quarter in `[start, end]`."""
        dates: list[dt.date] = []
        for year in range(start.year, end.year + 1):
            for month in _QUARTER_START_MONTHS:
                rolled = roll_to_trading_day(dt.date(year, month, 1))
                if start <= rolled <= end:
                    dates.append(rolled)
        return dates

    def target_weights(self, ctx: StrategyContext) -> dict[str, float]:
        """Equal-weight universe members with valid price and recent positive volume."""
        available = self._available_tickers(ctx.universe, ctx.as_of_date)
        frozen = {
            ticker: weight
            for ticker, weight in ctx.current_weights.items()
            if ticker in ctx.universe and ticker not in available and weight > 0.0
        }
        if not available:
            return frozen

        tradable_budget = max(1.0 - sum(frozen.values()), 0.0)
        weight = tradable_budget / len(available)
        return dict.fromkeys(available, weight) | frozen

    def _available_tickers(self, universe: list[str], as_of_date: dt.date) -> list[str]:
        """Filter out universe members missing price data at the signal date."""
        ordered_universe = list(dict.fromkeys(universe))
        if not ordered_universe:
            return []

        window_start = as_of_date - dt.timedelta(days=_LIQUIDITY_LOOKBACK_DAYS)
        prices = self.data.get_prices(
            tickers=ordered_universe,
            start=window_start,
            end=as_of_date,
            fields=("close", "volume"),
        )
        if prices.empty or not {"close", "volume"}.issubset(prices.columns):
            return []

        prices = prices.copy()
        prices["date"] = pd.to_datetime(prices["date"]).dt.date

        close_valid = set(
            prices.loc[
                (prices["date"] == as_of_date) & prices["close"].notna(),
                "ticker",
            ].astype(str)
        )
        volume = prices.loc[prices["volume"].notna(), ["ticker", "volume"]].copy()
        volume["volume"] = pd.to_numeric(volume["volume"], errors="coerce")
        positive_volume = volume[volume["volume"] > 0.0]
        positive_counts = positive_volume.groupby("ticker")["volume"].count()
        volume_medians = volume.groupby("ticker")["volume"].median()
        liquid = {
            str(ticker)
            for ticker in volume_medians.index
            if positive_counts.get(ticker, 0) >= _MIN_POSITIVE_VOLUME_OBSERVATIONS
            and volume_medians.loc[ticker] > 0.0
        }
        valid = close_valid & liquid
        return [ticker for ticker in ordered_universe if ticker in valid]
