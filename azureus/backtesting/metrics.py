"""Performance metrics for daily backtest return series.

All return-based metrics consume **daily** returns and annualize with 252
trading days, per ARCHITECTURE §4.9 and the project convention that Sharpe
must never be computed from monthly returns.
"""

from __future__ import annotations

import datetime as dt
import math
from typing import cast

import numpy as np
import pandas as pd

TRADING_DAYS_PER_YEAR = 252


def _clean_series(values: pd.Series) -> pd.Series:
    """Numeric float series with NaN/inf removed."""
    series = pd.to_numeric(values, errors="coerce").astype(float)
    return series[np.isfinite(series)]


def _to_date(value: object) -> dt.date:
    """Convert a pandas/datetime index value to `dt.date`."""
    if isinstance(value, pd.Timestamp):
        return value.date()
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    raise TypeError(f"expected date-like index value, got {type(value).__name__}")


def _index_position(series: pd.Series, label: object) -> int:
    """Integer position for a unique index label."""
    position = series.index.get_loc(label)
    if isinstance(position, int):
        return position
    raise ValueError(f"expected unique index label, got non-scalar position for {label!r}")


def annualized_return(returns: pd.Series) -> float:
    """Geometric annualized return from daily decimal returns."""
    clean = _clean_series(returns)
    if clean.empty:
        return math.nan
    cumulative = float(cast(float, (1.0 + clean).prod()))
    if cumulative <= 0:
        return -1.0
    result = cumulative ** (TRADING_DAYS_PER_YEAR / len(clean)) - 1.0
    return float(result)


def annualized_vol(returns: pd.Series) -> float:
    """Annualized volatility from daily return standard deviation."""
    clean = _clean_series(returns)
    if len(clean) < 2:
        return 0.0
    vol = float(clean.std(ddof=1) * math.sqrt(TRADING_DAYS_PER_YEAR))
    return 0.0 if math.isclose(vol, 0.0, abs_tol=1e-12) else vol


def sharpe(returns: pd.Series, rf: float = 0.0) -> float:
    """Annualized Sharpe ratio from daily returns.

    Args:
        returns: Daily decimal returns.
        rf: Annual risk-free rate, as a decimal. Converted to a daily
            arithmetic rate for excess-return calculation.
    """
    clean = _clean_series(returns)
    if clean.empty:
        return math.nan
    excess = clean - rf / TRADING_DAYS_PER_YEAR
    vol = annualized_vol(excess)
    annualized_excess = float(excess.mean() * TRADING_DAYS_PER_YEAR)
    if vol == 0.0:
        if annualized_excess > 0:
            return math.inf
        if annualized_excess < 0:
            return -math.inf
        return 0.0
    return annualized_excess / vol


def sortino(returns: pd.Series, rf: float = 0.0) -> float:
    """Annualized Sortino ratio from daily returns."""
    clean = _clean_series(returns)
    if clean.empty:
        return math.nan
    excess = clean - rf / TRADING_DAYS_PER_YEAR
    downside = excess[excess < 0.0]
    annualized_excess = float(excess.mean() * TRADING_DAYS_PER_YEAR)
    if downside.empty:
        if annualized_excess > 0:
            return math.inf
        if annualized_excess < 0:
            return -math.inf
        return 0.0
    downside_vol = float(downside.std(ddof=1) * math.sqrt(TRADING_DAYS_PER_YEAR))
    if downside_vol == 0.0:
        return math.inf if annualized_excess > 0 else 0.0
    return annualized_excess / downside_vol


def calmar(annualized_ret: float, max_dd: float) -> float:
    """Calmar ratio: annualized return divided by absolute max drawdown."""
    if max_dd == 0.0:
        if annualized_ret > 0:
            return math.inf
        if annualized_ret < 0:
            return -math.inf
        return 0.0
    return annualized_ret / abs(max_dd)


def drawdown_series(equity: pd.Series) -> pd.Series:
    """Running drawdown series, as negative decimal values from prior peak."""
    clean = _clean_series(equity)
    if clean.empty:
        return pd.Series(dtype=float)
    running_peak = clean.cummax()
    return clean / running_peak - 1.0


def max_drawdown_with_duration(
    equity: pd.Series,
) -> tuple[float, dt.date | None, dt.date | None, dt.date | None, int]:
    """Return max drawdown depth and peak-to-recovery duration.

    Returns:
        Tuple of `(depth, peak_date, trough_date, recovery_date, duration_days)`.
        `depth` is negative. If the series never recovers, `recovery_date` is
        `None` and `duration_days` counts from peak to the last observation.
    """
    clean = _clean_series(equity)
    if clean.empty:
        return 0.0, None, None, None, 0

    dd = drawdown_series(clean)
    trough_label = dd.idxmin()
    depth = float(dd.loc[trough_label])
    if depth == 0.0:
        first_date = _to_date(clean.index[0])
        return 0.0, first_date, first_date, first_date, 0

    trough_position = _index_position(clean, trough_label)
    pre_trough = clean.iloc[: trough_position + 1]
    peak_label = pre_trough.idxmax()
    peak_position = _index_position(clean, peak_label)
    peak_value = float(clean.loc[peak_label])

    recovery_date: dt.date | None = None
    duration_end = _to_date(clean.index[-1])
    for label, value in clean.iloc[trough_position + 1 :].items():
        if float(value) >= peak_value:
            recovery_date = _to_date(label)
            duration_end = recovery_date
            break

    peak_date = _to_date(clean.index[peak_position])
    trough_date = _to_date(trough_label)
    duration_days = (duration_end - peak_date).days
    return depth, peak_date, trough_date, recovery_date, duration_days


def turnover(weight_series: pd.DataFrame) -> pd.Series:
    """One-way turnover from a wide date × ticker weight matrix."""
    if weight_series.empty:
        return pd.Series(dtype=float)
    weights = weight_series.fillna(0.0).sort_index()
    return weights.diff().abs().sum(axis=1).fillna(0.0) / 2.0


def positive_month_fraction(returns: pd.Series) -> float:
    """Fraction of calendar months with positive compounded returns."""
    clean = _clean_series(returns)
    if clean.empty:
        return math.nan
    monthly = (1.0 + clean).resample("ME").prod() - 1.0
    if monthly.empty:
        return math.nan
    return float((monthly > 0.0).mean())


def skew(returns: pd.Series) -> float:
    """Daily return skewness."""
    clean = _clean_series(returns)
    return float(cast(float, clean.skew())) if len(clean) >= 3 else math.nan


def kurtosis(returns: pd.Series) -> float:
    """Daily return excess kurtosis."""
    clean = _clean_series(returns)
    return float(cast(float, clean.kurt())) if len(clean) >= 4 else math.nan
