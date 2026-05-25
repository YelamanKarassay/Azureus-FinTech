"""Fundamental value and quality features for Strategy 1."""

from __future__ import annotations

import datetime as dt

import pandas as pd

from azureus.data.sources.base import DataSource
from azureus.features.registry import register

_FUNDAMENTAL_LOOKBACK_DAYS = 550
_PRICE_LOOKBACK_DAYS = 31
_TTM_PERIODS = 4


class EarningsYield:
    """TTM net income divided by market capitalization."""

    name = "earnings_yield"
    description = "Trailing-twelve-month net income divided by market capitalization."
    family = "value"
    requires_metrics: tuple[str, ...] = ("net_income", "ordinary_shares")
    requires_lookback_days = _FUNDAMENTAL_LOOKBACK_DAYS

    def compute(
        self,
        data: DataSource,
        tickers: list[str],
        as_of_date: dt.date,
    ) -> pd.Series:
        net_income = _ttm_metric(data, tickers, as_of_date, "net_income")
        market_cap = _market_cap(data, tickers, as_of_date)
        return _ratio(net_income, market_cap, self.name)


class BookToPrice:
    """Book value divided by market capitalization."""

    name = "book_to_price"
    description = "Latest book value divided by market capitalization."
    family = "value"
    requires_metrics: tuple[str, ...] = ("book_value", "ordinary_shares")
    requires_lookback_days = _FUNDAMENTAL_LOOKBACK_DAYS

    def compute(
        self,
        data: DataSource,
        tickers: list[str],
        as_of_date: dt.date,
    ) -> pd.Series:
        fundamentals = _fundamental_snapshot(data, tickers, as_of_date, ["book_value"])
        market_cap = _market_cap(data, tickers, as_of_date)
        return _ratio(fundamentals["book_value"], market_cap, self.name)


class SalesToPrice:
    """TTM revenue divided by market capitalization."""

    name = "sales_to_price"
    description = "Trailing-twelve-month revenue divided by market capitalization."
    family = "value"
    requires_metrics: tuple[str, ...] = ("total_revenue", "ordinary_shares")
    requires_lookback_days = _FUNDAMENTAL_LOOKBACK_DAYS

    def compute(
        self,
        data: DataSource,
        tickers: list[str],
        as_of_date: dt.date,
    ) -> pd.Series:
        revenue = _ttm_metric(data, tickers, as_of_date, "total_revenue")
        market_cap = _market_cap(data, tickers, as_of_date)
        return _ratio(revenue, market_cap, self.name)


class FcfToPrice:
    """TTM free cash flow divided by market capitalization."""

    name = "fcf_to_price"
    description = "Trailing-twelve-month free cash flow divided by market capitalization."
    family = "value"
    requires_metrics: tuple[str, ...] = ("free_cash_flow", "ordinary_shares")
    requires_lookback_days = _FUNDAMENTAL_LOOKBACK_DAYS

    def compute(
        self,
        data: DataSource,
        tickers: list[str],
        as_of_date: dt.date,
    ) -> pd.Series:
        free_cash_flow = _ttm_metric(data, tickers, as_of_date, "free_cash_flow")
        market_cap = _market_cap(data, tickers, as_of_date)
        return _ratio(free_cash_flow, market_cap, self.name)


class Roe:
    """TTM net income divided by latest book value."""

    name = "roe"
    description = "Trailing-twelve-month net income divided by latest book value."
    family = "quality"
    requires_metrics: tuple[str, ...] = ("net_income", "book_value")
    requires_lookback_days = _FUNDAMENTAL_LOOKBACK_DAYS

    def compute(
        self,
        data: DataSource,
        tickers: list[str],
        as_of_date: dt.date,
    ) -> pd.Series:
        net_income = _ttm_metric(data, tickers, as_of_date, "net_income")
        fundamentals = _fundamental_snapshot(data, tickers, as_of_date, ["book_value"])
        return _ratio(net_income, fundamentals["book_value"], self.name)


class GrossProfitability:
    """TTM gross profit divided by latest total assets."""

    name = "gross_profitability"
    description = "Trailing-twelve-month gross profit divided by latest total assets."
    family = "quality"
    requires_metrics: tuple[str, ...] = ("gross_profit", "total_assets")
    requires_lookback_days = _FUNDAMENTAL_LOOKBACK_DAYS

    def compute(
        self,
        data: DataSource,
        tickers: list[str],
        as_of_date: dt.date,
    ) -> pd.Series:
        gross_profit = _ttm_metric(data, tickers, as_of_date, "gross_profit")
        fundamentals = _fundamental_snapshot(data, tickers, as_of_date, ["total_assets"])
        return _ratio(gross_profit, fundamentals["total_assets"], self.name)


class DebtToEquity:
    """Debt-to-equity, sign-flipped so lower leverage ranks higher."""

    name = "debt_to_equity"
    description = "Negative latest total debt divided by latest book value."
    family = "quality"
    requires_metrics: tuple[str, ...] = ("total_debt", "book_value")
    requires_lookback_days = _FUNDAMENTAL_LOOKBACK_DAYS

    def compute(
        self,
        data: DataSource,
        tickers: list[str],
        as_of_date: dt.date,
    ) -> pd.Series:
        fundamentals = _fundamental_snapshot(
            data,
            tickers,
            as_of_date,
            ["total_debt", "book_value"],
        )
        return -_ratio(fundamentals["total_debt"], fundamentals["book_value"], self.name)


class Accruals:
    """Accruals, sign-flipped so cash-backed earnings rank higher."""

    name = "accruals"
    description = "Negative accruals: operating cash flow less net income over total assets."
    family = "quality"
    requires_metrics: tuple[str, ...] = ("net_income", "operating_cash_flow", "total_assets")
    requires_lookback_days = _FUNDAMENTAL_LOOKBACK_DAYS

    def compute(
        self,
        data: DataSource,
        tickers: list[str],
        as_of_date: dt.date,
    ) -> pd.Series:
        net_income = _ttm_metric(data, tickers, as_of_date, "net_income")
        operating_cash_flow = _ttm_metric(
            data,
            tickers,
            as_of_date,
            "operating_cash_flow",
        )
        fundamentals = _fundamental_snapshot(data, tickers, as_of_date, ["total_assets"])
        cash_backed_earnings = operating_cash_flow.subtract(net_income, fill_value=float("nan"))
        return _ratio(cash_backed_earnings, fundamentals["total_assets"], self.name)


def _fundamental_snapshot(
    data: DataSource,
    tickers: list[str],
    as_of_date: dt.date,
    metrics: list[str],
) -> pd.DataFrame:
    if not tickers or not metrics:
        return pd.DataFrame(index=pd.Index([], name="ticker"))
    df = data.get_fundamentals(tickers=tickers, as_of_date=as_of_date, metrics=metrics)
    if df.empty:
        return pd.DataFrame(index=pd.Index([], name="ticker"), columns=metrics, dtype="float64")

    frame = df.copy()
    frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
    snapshot = frame.pivot_table(index="ticker", columns="metric", values="value", aggfunc="last")
    return snapshot.reindex(columns=metrics).astype(float)


def _ttm_metric(
    data: DataSource,
    tickers: list[str],
    as_of_date: dt.date,
    metric: str,
) -> pd.Series:
    if not tickers:
        return _feature_series({}, metric)
    df = data.get_fundamentals_history(
        tickers=tickers,
        start=as_of_date - dt.timedelta(days=_FUNDAMENTAL_LOOKBACK_DAYS),
        end=as_of_date,
        metrics=[metric],
    )
    if df.empty:
        return _feature_series({}, metric)

    frame = df.loc[df["metric"] == metric].copy()
    if frame.empty:
        return _feature_series({}, metric)
    frame["period_end"] = pd.to_datetime(frame["period_end"])
    frame["reported_date"] = pd.to_datetime(frame["reported_date"])
    frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
    frame = frame.dropna(subset=["period_end", "reported_date", "value"])

    latest_per_period = (
        frame.sort_values(["ticker", "period_end", "reported_date"])
        .drop_duplicates(["ticker", "period_end"], keep="last")
        .sort_values(["ticker", "period_end"], ascending=[True, False])
        .groupby("ticker", group_keys=False)
        .head(_TTM_PERIODS)
    )
    counts = latest_per_period.groupby("ticker")["value"].size()
    complete_tickers = counts[counts >= _TTM_PERIODS].index
    values = latest_per_period[latest_per_period["ticker"].isin(complete_tickers)]
    series = values.groupby("ticker")["value"].sum().astype(float)
    series.name = metric
    return series


def _market_cap(data: DataSource, tickers: list[str], as_of_date: dt.date) -> pd.Series:
    fundamentals = _fundamental_snapshot(data, tickers, as_of_date, ["ordinary_shares"])
    prices = _latest_prices(data, tickers, as_of_date)
    aligned = pd.concat(
        [
            _positive(fundamentals["ordinary_shares"]).rename("shares"),
            _positive(prices).rename("price"),
        ],
        axis=1,
        join="inner",
    ).dropna()
    values = (aligned["shares"] * aligned["price"]).astype(float)
    values.name = "market_cap"
    return values


def _latest_prices(data: DataSource, tickers: list[str], as_of_date: dt.date) -> pd.Series:
    if not tickers:
        return _feature_series({}, "price")
    df = data.get_prices(
        tickers=tickers,
        start=as_of_date - dt.timedelta(days=_PRICE_LOOKBACK_DAYS),
        end=as_of_date,
        fields=("adjusted_close", "close"),
    )
    if df.empty:
        return _feature_series({}, "price")

    frame = df.copy()
    frame["date"] = pd.to_datetime(frame["date"])
    adjusted = pd.to_numeric(frame["adjusted_close"], errors="coerce")
    close = pd.to_numeric(frame["close"], errors="coerce")
    frame["price"] = adjusted.fillna(close)
    frame = frame.dropna(subset=["date", "price"])
    latest = frame.sort_values(["ticker", "date"]).drop_duplicates("ticker", keep="last")
    series = latest.set_index("ticker")["price"].astype(float)
    series.name = "price"
    return series


def _ratio(numerator: pd.Series, denominator: pd.Series, name: str) -> pd.Series:
    aligned = pd.concat(
        [numerator.rename("numerator"), denominator.rename("denominator")],
        axis=1,
        join="inner",
    ).dropna()
    aligned = aligned[aligned["denominator"] > 0.0]
    values = (aligned["numerator"] / aligned["denominator"]).astype(float)
    values.name = name
    return values


def _positive(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    return values.where(values > 0.0).astype(float)


def _feature_series(values: dict[str, float], name: str) -> pd.Series:
    series = pd.Series(values, dtype="float64")
    series.name = name
    return series


earnings_yield = register(EarningsYield())
book_to_price = register(BookToPrice())
sales_to_price = register(SalesToPrice())
fcf_to_price = register(FcfToPrice())
roe = register(Roe())
gross_profitability = register(GrossProfitability())
debt_to_equity = register(DebtToEquity())
accruals = register(Accruals())
