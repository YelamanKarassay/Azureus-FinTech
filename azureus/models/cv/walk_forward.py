"""Expanding-window walk-forward utilities."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass


@dataclass(frozen=True)
class WalkForwardWindow:
    """One expanding-train / fixed-OOS walk-forward window."""

    window_id: str
    train_start: dt.date
    train_end: dt.date
    oos_start: dt.date
    oos_end: dt.date


def expanding_windows(
    *,
    start: dt.date,
    end: dt.date,
    warmup_years: int,
    oos_window_months: int,
) -> list[WalkForwardWindow]:
    """Build expanding walk-forward windows for a backtest interval."""
    if warmup_years < 1:
        raise ValueError("warmup_years must be positive")
    if oos_window_months < 1:
        raise ValueError("oos_window_months must be positive")

    oos_start = _add_years(start, warmup_years)
    windows: list[WalkForwardWindow] = []
    idx = 1
    while oos_start <= end:
        oos_end = min(_add_months(oos_start, oos_window_months) - dt.timedelta(days=1), end)
        train_end = oos_start - dt.timedelta(days=1)
        windows.append(
            WalkForwardWindow(
                window_id=f"wf_{idx:03d}",
                train_start=start,
                train_end=train_end,
                oos_start=oos_start,
                oos_end=oos_end,
            )
        )
        idx += 1
        oos_start = oos_end + dt.timedelta(days=1)
    return windows


def _add_years(value: dt.date, years: int) -> dt.date:
    try:
        return value.replace(year=value.year + years)
    except ValueError:
        return value.replace(month=2, day=28, year=value.year + years)


def _add_months(value: dt.date, months: int) -> dt.date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, _days_in_month(year, month))
    return dt.date(year, month, day)


def _days_in_month(year: int, month: int) -> int:
    next_month = dt.date(year + 1, 1, 1) if month == 12 else dt.date(year, month + 1, 1)
    return (next_month - dt.timedelta(days=1)).day
