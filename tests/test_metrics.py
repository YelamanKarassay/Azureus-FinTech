"""Unit tests for daily-return performance metrics."""

from __future__ import annotations

import datetime as dt
import math

import pandas as pd
import pytest

from azureus.backtesting.metrics import (
    annualized_return,
    annualized_vol,
    calmar,
    drawdown_series,
    max_drawdown_with_duration,
    sharpe,
    turnover,
)


def test_constant_positive_daily_return_has_infinite_sharpe() -> None:
    returns = pd.Series([0.01] * 10)

    assert sharpe(returns) == math.inf


def test_annualized_return_is_geometric_from_daily_returns() -> None:
    returns = pd.Series([0.01, 0.01])
    expected = (1.01**2) ** (252 / 2) - 1.0

    assert annualized_return(returns) == pytest.approx(expected)


def test_annualized_vol_uses_daily_sample_stdev() -> None:
    returns = pd.Series([0.01, -0.01, 0.02, -0.02])
    expected = returns.std(ddof=1) * math.sqrt(252)

    assert annualized_vol(returns) == pytest.approx(expected)


def test_drawdown_series_is_negative_from_running_peak() -> None:
    dates = pd.date_range("2024-01-01", periods=4)
    equity = pd.Series([100.0, 110.0, 99.0, 120.0], index=dates)

    dd = drawdown_series(equity)

    assert dd.iloc[0] == 0.0
    assert dd.iloc[1] == 0.0
    assert dd.iloc[2] == pytest.approx(-0.10)
    assert dd.iloc[3] == 0.0


def test_max_drawdown_duration_counts_peak_to_recovery() -> None:
    dates = pd.date_range("2024-01-01", periods=5)
    equity = pd.Series([100.0, 90.0, 80.0, 90.0, 100.0], index=dates)

    depth, peak, trough, recovery, duration_days = max_drawdown_with_duration(equity)

    assert depth == pytest.approx(-0.20)
    assert peak == dt.date(2024, 1, 1)
    assert trough == dt.date(2024, 1, 3)
    assert recovery == dt.date(2024, 1, 5)
    assert duration_days == 4


def test_max_drawdown_duration_counts_to_last_date_when_unrecovered() -> None:
    dates = pd.date_range("2024-01-01", periods=4)
    equity = pd.Series([100.0, 80.0, 85.0, 90.0], index=dates)

    depth, peak, trough, recovery, duration_days = max_drawdown_with_duration(equity)

    assert depth == pytest.approx(-0.20)
    assert peak == dt.date(2024, 1, 1)
    assert trough == dt.date(2024, 1, 2)
    assert recovery is None
    assert duration_days == 3


def test_calmar_divides_by_absolute_drawdown() -> None:
    assert calmar(0.12, -0.25) == pytest.approx(0.48)


def test_turnover_is_half_absolute_weight_change() -> None:
    weights = pd.DataFrame(
        {
            "0700.HK": [0.5, 0.2],
            "0005.HK": [0.0, 0.3],
        },
        index=pd.to_datetime(["2024-01-01", "2024-01-02"]),
    )

    values = turnover(weights)

    assert values.iloc[0] == 0.0
    assert values.iloc[1] == pytest.approx(0.3)
