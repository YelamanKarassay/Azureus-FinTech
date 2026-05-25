"""Market-price features for Strategy 1."""

from __future__ import annotations

import datetime as dt
import math

import pandas as pd

from azureus.data.sources.base import DataSource
from azureus.features.registry import register

_TRADING_DAYS_PER_YEAR = 252
_MOMENTUM_SKIP_DAYS = 21
_MOMENTUM_LOOKBACK_DAYS = 252
_FULL_YEAR_LOOKBACK_DAYS = 420
_MIN_BETA_OBSERVATIONS = 126


class Momentum121:
    """12-1 momentum: return from roughly 12 months ago to 1 month ago."""

    name = "momentum_12_1"
    description = "12-month momentum skipping the most recent month."
    family = "momentum"
    requires_metrics: tuple[str, ...] = ()
    requires_lookback_days = _FULL_YEAR_LOOKBACK_DAYS

    def compute(
        self,
        data: DataSource,
        tickers: list[str],
        as_of_date: dt.date,
    ) -> pd.Series:
        prices = _price_matrix(
            data,
            tickers,
            as_of_date - dt.timedelta(days=self.requires_lookback_days),
            as_of_date,
        )
        values: dict[str, float] = {}
        for ticker in tickers:
            if ticker not in prices.columns:
                continue
            series = prices[ticker].dropna()
            required = _MOMENTUM_LOOKBACK_DAYS + 1
            if len(series) < required:
                continue
            start_price = float(series.iloc[-required])
            end_price = float(series.iloc[-(_MOMENTUM_SKIP_DAYS + 1)])
            if start_price > 0.0 and end_price > 0.0:
                values[ticker] = end_price / start_price - 1.0
        return _feature_series(values, self.name)


class RealizedVol252D:
    """Annualized 252-day realized volatility, sign-flipped so lower vol ranks higher."""

    name = "realized_vol_252d"
    description = "Negative annualized 252-day realized volatility."
    family = "low_vol"
    requires_metrics: tuple[str, ...] = ()
    requires_lookback_days = _FULL_YEAR_LOOKBACK_DAYS

    def compute(
        self,
        data: DataSource,
        tickers: list[str],
        as_of_date: dt.date,
    ) -> pd.Series:
        prices = _price_matrix(
            data,
            tickers,
            as_of_date - dt.timedelta(days=self.requires_lookback_days),
            as_of_date,
        )
        values: dict[str, float] = {}
        for ticker in tickers:
            if ticker not in prices.columns:
                continue
            returns = prices[ticker].dropna().pct_change().dropna().tail(_TRADING_DAYS_PER_YEAR)
            if len(returns) < _TRADING_DAYS_PER_YEAR:
                continue
            vol = float(returns.std(ddof=1) * math.sqrt(_TRADING_DAYS_PER_YEAR))
            values[ticker] = -vol
        return _feature_series(values, self.name)


class Beta252D:
    """252-day beta to an equal-weight universe proxy, sign-flipped."""

    name = "beta_252d"
    description = "Negative 252-day beta to the equal-weight universe return."
    family = "low_vol"
    requires_metrics: tuple[str, ...] = ()
    requires_lookback_days = _FULL_YEAR_LOOKBACK_DAYS

    def compute(
        self,
        data: DataSource,
        tickers: list[str],
        as_of_date: dt.date,
    ) -> pd.Series:
        prices = _price_matrix(
            data,
            tickers,
            as_of_date - dt.timedelta(days=self.requires_lookback_days),
            as_of_date,
        )
        returns = prices.pct_change().dropna(how="all").tail(_TRADING_DAYS_PER_YEAR)
        if returns.empty:
            return _feature_series({}, self.name)

        market = returns.mean(axis=1, skipna=True)
        values: dict[str, float] = {}
        for ticker in tickers:
            if ticker not in returns.columns:
                continue
            aligned = pd.concat(
                [returns[ticker].rename("asset"), market.rename("market")],
                axis=1,
            ).dropna()
            if len(aligned) < _MIN_BETA_OBSERVATIONS:
                continue
            market_var = float(aligned["market"].var(ddof=1))
            if market_var == 0.0:
                continue
            cov = float(aligned["asset"].cov(aligned["market"]))
            values[ticker] = -(cov / market_var)
        return _feature_series(values, self.name)


def _price_matrix(
    data: DataSource,
    tickers: list[str],
    start: dt.date,
    end: dt.date,
) -> pd.DataFrame:
    """Return date × ticker adjusted-close matrix with close fallback."""
    if not tickers:
        return pd.DataFrame()
    df = data.get_prices(
        tickers=tickers,
        start=start,
        end=end,
        fields=("adjusted_close", "close"),
    )
    if df.empty:
        return pd.DataFrame()

    frame = df.copy()
    frame["date"] = pd.to_datetime(frame["date"])
    adjusted = pd.to_numeric(frame["adjusted_close"], errors="coerce")
    close = pd.to_numeric(frame["close"], errors="coerce")
    frame["price"] = adjusted.fillna(close)
    matrix = frame.pivot_table(index="date", columns="ticker", values="price", aggfunc="last")
    return matrix.sort_index().astype(float)


def _feature_series(values: dict[str, float], name: str) -> pd.Series:
    series = pd.Series(values, dtype="float64")
    series.name = name
    return series


momentum_12_1 = register(Momentum121())
realized_vol_252d = register(RealizedVol252D())
beta_252d = register(Beta252D())
