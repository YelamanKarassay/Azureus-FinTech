"""Strategy 2 focused unit tests."""

from __future__ import annotations

import datetime as dt

import pandas as pd

from azureus.models.gbm import spearman_ic, strategy2_param_grid
from azureus.strategies.gbm_factors_v1 import (
    GBMFactorsV1Params,
    GBMFactorsV1Strategy,
    _forward_sector_neutral_labels,
)
from azureus.utils.dates import trading_days_between


class _LabelDataSource:
    provider_name = "public_free"

    def __init__(self) -> None:
        start = dt.date(2024, 1, 2)
        end = trading_days_between(start, start + dt.timedelta(days=70))[21]
        rows = []
        for ticker, start_price, end_price in [
            ("0001.HK", 100.0, 110.0),
            ("0002.HK", 100.0, 105.0),
            ("0003.HK", 100.0, 90.0),
        ]:
            rows.append(
                {
                    "date": start,
                    "ticker": ticker,
                    "adjusted_close": start_price,
                    "close": start_price,
                }
            )
            rows.append(
                {
                    "date": end,
                    "ticker": ticker,
                    "adjusted_close": end_price,
                    "close": end_price,
                }
            )
        self.prices = pd.DataFrame(rows)

    def get_universe(self, index_id: str, as_of_date: dt.date) -> list[str]:
        return ["0001.HK", "0002.HK", "0003.HK"]

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
            self.prices["ticker"].isin(tickers)
            & (self.prices["date"] >= start)
            & (self.prices["date"] <= end)
        )
        return self.prices.loc[mask, ["date", "ticker", *fields]].copy()

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
        return ["0001.HK", "0002.HK", "0003.HK"]

    def list_available_metrics(self) -> list[str]:
        return []


def test_strategy2_param_grid_has_locked_24_combinations() -> None:
    grid = strategy2_param_grid()

    assert len(grid) == 24
    assert {params["feature_fraction"] for params in grid} == {0.8}
    assert {params["bagging_fraction"] for params in grid} == {0.8}


def test_spearman_ic_is_finite_for_ranked_predictions() -> None:
    ic = spearman_ic(
        pd.Series([0.1, 0.2, 0.3]),
        pd.Series([1.0, 2.0, 3.0]),
    )

    assert ic == 1.0


def test_forward_labels_are_sector_neutral() -> None:
    strategy = GBMFactorsV1Strategy(
        GBMFactorsV1Params(
            label_horizon_days=21,
            liquidity_threshold_usd=0,
            sector_map={
                "0001.HK": "Tech",
                "0002.HK": "Tech",
                "0003.HK": "Financials",
            },
        ),
        _LabelDataSource(),
    )

    labels = _forward_sector_neutral_labels(
        strategy=strategy,
        tickers=["0001.HK", "0002.HK", "0003.HK"],
        as_of_date=dt.date(2024, 1, 2),
        horizon_days=21,
    )

    assert labels.loc["0001.HK", "label"] > 0.0
    assert labels.loc["0002.HK", "label"] < 0.0
    assert abs(labels.loc["0003.HK", "label"]) < 1e-12
