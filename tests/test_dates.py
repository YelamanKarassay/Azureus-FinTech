"""HKEX trading calendar wrapper tests.

We don't re-verify the entire HK holiday calendar — `exchange-calendars`
is well-tested upstream. These tests assert our wrapper's behaviour at
boundaries: weekends, the New Year's Day holiday, a Lunar New Year
date, and the next/previous/roll semantics around them.
"""

from __future__ import annotations

import datetime as dt

import pytest

from azureus.utils.dates import (
    is_trading_day,
    next_trading_day,
    previous_trading_day,
    roll_to_trading_day,
    trading_days_between,
)

# ---- is_trading_day -------------------------------------------------------


def test_saturday_is_not_trading_day() -> None:
    # 2024-01-06 was a Saturday.
    assert not is_trading_day(dt.date(2024, 1, 6))


def test_sunday_is_not_trading_day() -> None:
    # 2024-01-07 was a Sunday.
    assert not is_trading_day(dt.date(2024, 1, 7))


def test_new_years_day_2024_not_trading() -> None:
    # 2024-01-01 was Monday + HK New Year holiday.
    assert not is_trading_day(dt.date(2024, 1, 1))


def test_normal_weekday_is_trading() -> None:
    # 2024-01-02 was a Tuesday, full HK trading session.
    assert is_trading_day(dt.date(2024, 1, 2))


def test_lunar_new_year_2024_not_trading() -> None:
    # 2024 LNY: HKEX was closed Mon 2024-02-12 and Tue 2024-02-13.
    assert not is_trading_day(dt.date(2024, 2, 12))
    assert not is_trading_day(dt.date(2024, 2, 13))


def test_christmas_2024_not_trading() -> None:
    # 2024-12-25 (Christmas) and 2024-12-26 (the day after) are HK holidays.
    assert not is_trading_day(dt.date(2024, 12, 25))
    assert not is_trading_day(dt.date(2024, 12, 26))


def test_ad_hoc_weather_closures_are_not_trading_days() -> None:
    """Known 2023 HKEX weather closures are filtered from the library calendar."""
    assert not is_trading_day(dt.date(2023, 9, 1))
    assert not is_trading_day(dt.date(2023, 9, 8))


# ---- next/previous -------------------------------------------------------


def test_next_trading_day_skips_weekend() -> None:
    # Friday 2024-01-05 → Monday 2024-01-08.
    assert next_trading_day(dt.date(2024, 1, 5)) == dt.date(2024, 1, 8)


def test_previous_trading_day_skips_weekend() -> None:
    # Monday 2024-01-08 → Friday 2024-01-05.
    assert previous_trading_day(dt.date(2024, 1, 8)) == dt.date(2024, 1, 5)


def test_next_trading_day_skips_new_year_holiday() -> None:
    # 2023-12-29 was the last 2023 trading day (Fri). 2024-01-01 was a
    # Monday holiday → next session is 2024-01-02 (Tue).
    assert next_trading_day(dt.date(2023, 12, 29)) == dt.date(2024, 1, 2)


def test_previous_trading_day_is_strictly_before() -> None:
    # 2024-01-03 (Wed) → 2024-01-02 (Tue), not 2024-01-03 itself.
    assert previous_trading_day(dt.date(2024, 1, 3)) == dt.date(2024, 1, 2)


def test_previous_trading_day_skips_ad_hoc_weather_closure() -> None:
    assert previous_trading_day(dt.date(2023, 9, 4)) == dt.date(2023, 8, 31)


# ---- roll_to_trading_day -------------------------------------------------


def test_roll_idempotent_on_trading_day() -> None:
    d = dt.date(2024, 1, 2)
    assert roll_to_trading_day(d) == d


def test_roll_advances_weekend_to_monday() -> None:
    # Saturday 2024-01-06 → Monday 2024-01-08.
    assert roll_to_trading_day(dt.date(2024, 1, 6)) == dt.date(2024, 1, 8)


def test_roll_advances_holiday_to_next_session() -> None:
    # New Year 2024-01-01 (Mon, holiday) → 2024-01-02 (Tue).
    assert roll_to_trading_day(dt.date(2024, 1, 1)) == dt.date(2024, 1, 2)


def test_roll_advances_multi_day_holiday_to_first_session() -> None:
    # LNY: Sat 2024-02-10 (start of LNY) → Wed 2024-02-14 (first session).
    # Mon 2024-02-12 and Tue 2024-02-13 are HK holidays.
    assert roll_to_trading_day(dt.date(2024, 2, 10)) == dt.date(2024, 2, 14)


def test_roll_advances_ad_hoc_weather_closure_to_next_session() -> None:
    assert roll_to_trading_day(dt.date(2023, 9, 1)) == dt.date(2023, 9, 4)


# ---- trading_days_between ------------------------------------------------


def test_trading_days_between_endpoints_inclusive() -> None:
    # 2024-01-02 and 2024-01-03 are both trading days; range of two trading
    # days inclusive should return both.
    days = trading_days_between(dt.date(2024, 1, 2), dt.date(2024, 1, 3))
    assert days == [dt.date(2024, 1, 2), dt.date(2024, 1, 3)]


def test_trading_days_between_january_2024_known_count() -> None:
    # Jan 2024: 31 calendar days. NYE holiday (Jan 1). Eight weekend days
    # (4 Saturdays: 6/13/20/27, 4 Sundays: 7/14/21/28). 31 - 1 - 8 = 22.
    days = trading_days_between(dt.date(2024, 1, 1), dt.date(2024, 1, 31))
    assert len(days) == 22
    assert dt.date(2024, 1, 1) not in days
    assert dt.date(2024, 1, 6) not in days  # Saturday
    assert dt.date(2024, 1, 2) in days  # Tuesday


def test_trading_days_between_empty_when_start_after_end() -> None:
    days = trading_days_between(dt.date(2024, 1, 10), dt.date(2024, 1, 5))
    assert days == []


@pytest.mark.parametrize(
    ("year", "month", "known_holiday_dates"),
    [
        (2024, 5, [dt.date(2024, 5, 1), dt.date(2024, 5, 15)]),  # Labour, Buddha's Birthday
        (2024, 10, [dt.date(2024, 10, 1), dt.date(2024, 10, 11)]),  # National, Chung Yeung
    ],
)
def test_known_holidays_excluded_from_trading_days(
    year: int,
    month: int,
    known_holiday_dates: list[dt.date],
) -> None:
    """Spot-check that exchange-calendars carries the HK holiday set we expect."""
    last_day = (
        dt.date(year, month + 1, 1) - dt.timedelta(days=1) if month < 12 else dt.date(year, 12, 31)
    )
    days = trading_days_between(dt.date(year, month, 1), last_day)
    for holiday in known_holiday_dates:
        assert holiday not in days, f"{holiday} should be a non-trading day"
