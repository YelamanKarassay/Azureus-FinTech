"""Fundamental feature and scoring helper tests."""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence

import pandas as pd
import pytest

from azureus.features import (
    accruals,
    book_to_price,
    debt_to_equity,
    earnings_yield,
    fcf_to_price,
    get_feature,
    gross_profitability,
    list_features,
    roe,
    sales_to_price,
)
from azureus.features.scoring import (
    composite_score,
    family_scores,
    feature_availability_filter,
    sector_rank_zscore,
)


class FundamentalFeatureDataSource:
    """Minimal in-memory DataSource for fundamental feature tests."""

    provider_name = "feature-test"

    def __init__(self, prices: pd.DataFrame, fundamentals: pd.DataFrame) -> None:
        self._prices = prices
        self._fundamentals = fundamentals

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
        frame = self._fundamentals
        mask = (
            frame["ticker"].isin(tickers)
            & frame["metric"].isin(metrics)
            & (frame["reported_date"] <= as_of_date)
        )
        filtered = frame.loc[mask].copy()
        return (
            filtered.sort_values(["ticker", "metric", "reported_date", "period_end"])
            .drop_duplicates(["ticker", "metric"], keep="last")
            .reset_index(drop=True)
        )

    def get_fundamentals_history(
        self,
        tickers: list[str],
        start: dt.date,
        end: dt.date,
        metrics: list[str],
    ) -> pd.DataFrame:
        frame = self._fundamentals
        mask = (
            frame["ticker"].isin(tickers)
            & frame["metric"].isin(metrics)
            & (frame["reported_date"] >= start)
            & (frame["reported_date"] <= end)
        )
        return frame.loc[mask].copy().reset_index(drop=True)

    def get_macro(self, series_ids: list[str], start: dt.date, end: dt.date) -> pd.DataFrame:
        return pd.DataFrame()

    def list_available_tickers(self, index_id: str | None = None) -> list[str]:
        return sorted(self._prices["ticker"].unique())

    def list_available_metrics(self) -> list[str]:
        return sorted(self._fundamentals["metric"].unique())


def _fundamental_feature_source() -> FundamentalFeatureDataSource:
    as_of_date = dt.date(2025, 3, 31)
    prices = pd.DataFrame(
        [
            {
                "date": pd.Timestamp(as_of_date),
                "provider": "yfinance",
                "ticker": ticker,
                "close": price,
                "adjusted_close": price,
            }
            for ticker, price in {"A.HK": 10.0, "B.HK": 20.0, "MISS.HK": 10.0}.items()
        ]
    )
    fundamentals = pd.DataFrame(
        [
            *_flow_rows(
                "A.HK",
                {
                    "net_income": [20.0, 25.0, 25.0, 30.0],
                    "total_revenue": [200.0, 200.0, 200.0, 200.0],
                    "gross_profit": [80.0, 80.0, 80.0, 80.0],
                    "free_cash_flow": [20.0, 20.0, 20.0, 20.0],
                    "operating_cash_flow": [30.0, 30.0, 30.0, 30.0],
                },
            ),
            *_snapshot_rows(
                "A.HK",
                {
                    "book_value": 500.0,
                    "total_assets": 1000.0,
                    "total_debt": 100.0,
                    "ordinary_shares": 100.0,
                },
            ),
            *_flow_rows(
                "B.HK",
                {
                    "net_income": [10.0, 10.0, 10.0, 10.0],
                    "total_revenue": [100.0, 100.0, 100.0, 100.0],
                    "gross_profit": [50.0, 50.0, 50.0, 50.0],
                    "free_cash_flow": [10.0, 10.0, 10.0, 10.0],
                    "operating_cash_flow": [8.0, 8.0, 8.0, 8.0],
                },
            ),
            *_snapshot_rows(
                "B.HK",
                {
                    "book_value": 400.0,
                    "total_assets": 800.0,
                    "total_debt": 400.0,
                    "ordinary_shares": 100.0,
                },
            ),
            *_flow_rows("MISS.HK", {"net_income": [5.0, 5.0, 5.0]}),
            *_snapshot_rows("MISS.HK", {"ordinary_shares": 100.0}),
        ]
    )
    return FundamentalFeatureDataSource(prices=prices, fundamentals=fundamentals)


def _flow_rows(ticker: str, metric_values: dict[str, Sequence[float]]) -> list[dict[str, object]]:
    periods = [
        dt.date(2024, 3, 31),
        dt.date(2024, 6, 30),
        dt.date(2024, 9, 30),
        dt.date(2024, 12, 31),
    ]
    rows: list[dict[str, object]] = []
    for metric, values in metric_values.items():
        for period_end, value in zip(periods, values, strict=False):
            rows.append(
                {
                    "provider": "yfinance",
                    "ticker": ticker,
                    "metric": metric,
                    "period_end": period_end,
                    "reported_date": period_end + dt.timedelta(days=90),
                    "value": value,
                    "unit": "currency",
                    "is_restated": False,
                }
            )
    return rows


def _snapshot_rows(ticker: str, metric_values: dict[str, float]) -> list[dict[str, object]]:
    return [
        {
            "provider": "yfinance",
            "ticker": ticker,
            "metric": metric,
            "period_end": dt.date(2024, 12, 31),
            "reported_date": dt.date(2025, 3, 31),
            "value": value,
            "unit": "currency",
            "is_restated": False,
        }
        for metric, value in metric_values.items()
    ]


def test_fundamental_features_are_registered() -> None:
    names = {feature.name for feature in list_features()}

    assert get_feature("earnings_yield") is earnings_yield
    assert {
        "earnings_yield",
        "book_to_price",
        "sales_to_price",
        "fcf_to_price",
        "roe",
        "gross_profitability",
        "debt_to_equity",
        "accruals",
    } <= names


def test_value_features_compute_sparse_ratios_without_imputation() -> None:
    data = _fundamental_feature_source()
    as_of_date = dt.date(2025, 3, 31)
    tickers = ["A.HK", "B.HK", "MISS.HK"]

    assert earnings_yield.compute(data, tickers, as_of_date)["A.HK"] == pytest.approx(0.10)
    assert book_to_price.compute(data, tickers, as_of_date)["A.HK"] == pytest.approx(0.50)
    assert sales_to_price.compute(data, tickers, as_of_date)["A.HK"] == pytest.approx(0.80)
    assert fcf_to_price.compute(data, tickers, as_of_date)["A.HK"] == pytest.approx(0.08)

    values = earnings_yield.compute(data, tickers, as_of_date)
    assert "MISS.HK" not in values.index


def test_quality_features_compute_sign_flipped_ratios() -> None:
    data = _fundamental_feature_source()
    as_of_date = dt.date(2025, 3, 31)
    tickers = ["A.HK", "B.HK"]

    assert roe.compute(data, tickers, as_of_date)["A.HK"] == pytest.approx(0.20)
    assert gross_profitability.compute(data, tickers, as_of_date)["A.HK"] == pytest.approx(0.32)
    assert debt_to_equity.compute(data, tickers, as_of_date)["A.HK"] == pytest.approx(-0.20)
    assert accruals.compute(data, tickers, as_of_date)["A.HK"] == pytest.approx(0.02)

    leverage = debt_to_equity.compute(data, tickers, as_of_date)
    assert leverage["A.HK"] > leverage["B.HK"]


def test_feature_availability_filter_requires_complete_rows() -> None:
    features = {
        "earnings_yield": pd.Series({"A.HK": 0.1, "B.HK": 0.2, "MISS.HK": 0.3}),
        "roe": pd.Series({"A.HK": 0.2, "B.HK": 0.1}),
    }

    assert feature_availability_filter(features, tickers=["A.HK", "B.HK", "MISS.HK"]) == [
        "A.HK",
        "B.HK",
    ]


def test_sector_rank_zscore_ranks_within_sector() -> None:
    values = pd.Series(
        {"A.HK": 3.0, "B.HK": 1.0, "C.HK": 2.0, "D.HK": 4.0},
        name="feature",
    )
    sectors = {"A.HK": "Tech", "B.HK": "Tech", "C.HK": "Finance", "D.HK": "Finance"}

    scores = sector_rank_zscore(values, sectors=sectors)

    assert scores["A.HK"] == pytest.approx(scores["D.HK"])
    assert scores["B.HK"] == pytest.approx(scores["C.HK"])
    assert scores["A.HK"] > scores["B.HK"]


def test_family_and_composite_scores_use_complete_feature_matrix() -> None:
    features = {
        "earnings_yield": pd.Series({"A.HK": 0.10, "B.HK": 0.02, "MISS.HK": 0.30}),
        "roe": pd.Series({"A.HK": 0.20, "B.HK": 0.10}),
    }
    families = {"earnings_yield": "value", "roe": "quality"}

    scores = family_scores(
        features,
        feature_families=families,
        sectors={"A.HK": "Tech", "B.HK": "Tech", "MISS.HK": "Tech"},
        tickers=["A.HK", "B.HK", "MISS.HK"],
    )
    composite = composite_score(scores, {"value": 0.5, "quality": 0.5})

    assert list(scores.index) == ["A.HK", "B.HK"]
    assert composite["A.HK"] > composite["B.HK"]
