"""Market feature tests for Phase 3 Strategy 1 inputs."""

from __future__ import annotations

import datetime as dt

import pandas as pd
import pytest

from azureus.features import get_feature, list_features
from azureus.features.market import beta_252d, momentum_12_1, realized_vol_252d


class PriceFeatureDataSource:
    """Minimal in-memory DataSource for market feature tests."""

    provider_name = "feature-test"

    def __init__(self, prices: pd.DataFrame) -> None:
        self._prices = prices

    def get_universe(self, index_id: str, as_of_date: dt.date) -> list[str]:
        return sorted(self._prices["ticker"].unique())

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
        columns = ["date", "provider", "ticker", *fields]
        return self._prices.loc[mask, columns].copy()

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
        return sorted(self._prices["ticker"].unique())

    def list_available_metrics(self) -> list[str]:
        return []


def _market_feature_source() -> PriceFeatureDataSource:
    dates = pd.bdate_range("2023-01-02", periods=280)
    rows: list[dict[str, object]] = []
    for i, day in enumerate(dates):
        base = 100.0 * (1.001**i)
        prices = {
            "UP.HK": base,
            "FLAT.HK": 100.0,
            "VOL.HK": 100.0 * (1.0 + 0.03 * ((-1) ** i)) * (1.0005**i),
            "HIGHBETA.HK": 100.0 * (1.002**i),
            "LOWBETA.HK": 100.0 * (1.0004**i),
        }
        for ticker, price in prices.items():
            rows.append(
                {
                    "date": day,
                    "provider": "yfinance",
                    "ticker": ticker,
                    "close": price,
                    "adjusted_close": price,
                    "volume": 1_000_000,
                }
            )
    return PriceFeatureDataSource(pd.DataFrame(rows))


def test_market_features_are_registered() -> None:
    names = {feature.name for feature in list_features()}

    assert get_feature("momentum_12_1") is momentum_12_1
    assert {"momentum_12_1", "realized_vol_252d", "beta_252d"} <= names


def test_momentum_12_1_orders_trending_ticker_above_flat() -> None:
    data = _market_feature_source()

    values = momentum_12_1.compute(
        data=data,
        tickers=["UP.HK", "FLAT.HK"],
        as_of_date=dt.date(2024, 1, 26),
    )

    assert values["UP.HK"] > values["FLAT.HK"]
    assert values["FLAT.HK"] == pytest.approx(0.0)


def test_realized_vol_252d_is_sign_flipped() -> None:
    data = _market_feature_source()

    values = realized_vol_252d.compute(
        data=data,
        tickers=["UP.HK", "VOL.HK"],
        as_of_date=dt.date(2024, 1, 26),
    )

    assert values["UP.HK"] > values["VOL.HK"]
    assert values["VOL.HK"] < 0.0


def test_beta_252d_is_sign_flipped() -> None:
    data = _market_feature_source()

    values = beta_252d.compute(
        data=data,
        tickers=["HIGHBETA.HK", "LOWBETA.HK", "UP.HK"],
        as_of_date=dt.date(2024, 1, 26),
    )

    assert values["LOWBETA.HK"] > values["HIGHBETA.HK"]
    assert values["HIGHBETA.HK"] < 0.0


def test_market_features_exclude_tickers_with_insufficient_history() -> None:
    data = _market_feature_source()

    values = momentum_12_1.compute(
        data=data,
        tickers=["UP.HK"],
        as_of_date=dt.date(2023, 2, 1),
    )

    assert values.empty
