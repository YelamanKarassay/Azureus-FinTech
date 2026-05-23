"""HKEX trading calendar helpers.

Thin wrapper around `exchange-calendars` so callers get plain `dt.date`
values and a small, opinionated API. Holiday handling is delegated to
the calendar library — HK's holiday set is non-trivial (Lunar New Year,
Buddha's Birthday, Tuen Ng, Mid-Autumn, Chung Yeung, etc.) and shifts
year-to-year.

Convention used throughout the backtesting engine:
- A *rebalance date* may be specified on any calendar day. If it's not
  a trading day (holiday or weekend), `roll_to_trading_day` advances
  it to the next trading day. The engine never executes trades on
  non-trading days.
- `next_trading_day(d)` is strictly the trading day *after* `d`, even
  if `d` is itself a trading day. Same for `previous_trading_day`.

Implementation note: `exchange_calendars`'s `next_session(d)` requires
`d` to itself be a valid session, which is awkward for our use case
(we frequently look up "next session on or after a weekend / holiday").
We use `sessions_in_range` instead — well-defined for any calendar date.
"""

from __future__ import annotations

import datetime as dt
from functools import lru_cache
from typing import cast

import exchange_calendars as ec
import pandas as pd

_HKEX_CALENDAR_NAME = "XHKG"  # ISO 10383 MIC code for HKEX
_LOOKUP_WINDOW = pd.Timedelta(days=21)  # generous buffer for multi-day holidays


@lru_cache(maxsize=1)
def _hkex_calendar() -> ec.ExchangeCalendar:
    return ec.get_calendar(_HKEX_CALENDAR_NAME)


def _next_session_on_or_after(d: dt.date) -> dt.date:
    """Internal: first session whose date is `>= d`. Raises if none within window."""
    cal = _hkex_calendar()
    start = pd.Timestamp(d)
    sessions = cal.sessions_in_range(start, start + _LOOKUP_WINDOW)
    if len(sessions) == 0:
        raise ValueError(f"no HKEX trading day found within 21 days from {d}")
    # pandas-stubs types Timestamp.date() as Any — pin it explicitly.
    return cast(dt.date, sessions[0].date())


def is_trading_day(d: dt.date) -> bool:
    """`True` iff HKEX has a trading session on `d`."""
    return bool(_hkex_calendar().is_session(pd.Timestamp(d)))


def trading_days_between(start: dt.date, end: dt.date) -> list[dt.date]:
    """Trading days in `[start, end]` (both endpoints inclusive)."""
    if start > end:
        return []
    sessions = _hkex_calendar().sessions_in_range(pd.Timestamp(start), pd.Timestamp(end))
    return [ts.date() for ts in sessions]


def next_trading_day(d: dt.date) -> dt.date:
    """The trading day strictly after `d` (irrespective of whether `d` itself is a session)."""
    return _next_session_on_or_after(d + dt.timedelta(days=1))


def previous_trading_day(d: dt.date) -> dt.date:
    """The trading day strictly before `d`."""
    cal = _hkex_calendar()
    end = pd.Timestamp(d) - pd.Timedelta(days=1)
    start = end - _LOOKUP_WINDOW
    sessions = cal.sessions_in_range(start, end)
    if len(sessions) == 0:
        raise ValueError(f"no HKEX trading day found within 21 days before {d}")
    return cast(dt.date, sessions[-1].date())


def roll_to_trading_day(d: dt.date) -> dt.date:
    """Return `d` if it's a trading day, else the next trading day on or after `d`.

    Used to normalise rebalance dates that may fall on holidays or
    weekends — the engine never trades on a non-session day.
    """
    return _next_session_on_or_after(d)
