"""Pandera schema unit tests — pure, no DB required.

Each test mutates the `synthetic_prices_df` fixture (defined in conftest.py)
to trigger one specific constraint, asserts the validator catches it, and
asserts the unmutated fixture passes.
"""

from __future__ import annotations

import datetime as dt

import pandas as pd
import pandera.errors
import pytest

from azureus.data.validators import PRICES_SCHEMA


def test_clean_dataframe_passes(synthetic_prices_df: pd.DataFrame) -> None:
    PRICES_SCHEMA.validate(synthetic_prices_df)


def test_rejects_negative_close(synthetic_prices_df: pd.DataFrame) -> None:
    df = synthetic_prices_df.copy()
    df.loc[0, "close"] = -1.0
    with pytest.raises(pandera.errors.SchemaError):
        PRICES_SCHEMA.validate(df)


def test_rejects_null_close(synthetic_prices_df: pd.DataFrame) -> None:
    df = synthetic_prices_df.copy()
    df.loc[0, "close"] = None
    with pytest.raises(pandera.errors.SchemaError):
        PRICES_SCHEMA.validate(df)


def test_rejects_high_less_than_low(synthetic_prices_df: pd.DataFrame) -> None:
    df = synthetic_prices_df.copy()
    df.loc[0, "high"] = 1.0
    df.loc[0, "low"] = 100.0
    with pytest.raises(pandera.errors.SchemaError):
        PRICES_SCHEMA.validate(df)


def test_rejects_future_dates(synthetic_prices_df: pd.DataFrame) -> None:
    df = synthetic_prices_df.copy()
    future = pd.Timestamp(dt.date.today() + dt.timedelta(days=365))
    df.loc[0, "date"] = future
    with pytest.raises(pandera.errors.SchemaError):
        PRICES_SCHEMA.validate(df)


def test_rejects_duplicate_keys(synthetic_prices_df: pd.DataFrame) -> None:
    df = pd.concat(
        [synthetic_prices_df, synthetic_prices_df.iloc[[0]]],
        ignore_index=True,
    )
    with pytest.raises(pandera.errors.SchemaError):
        PRICES_SCHEMA.validate(df)


def test_rejects_unknown_provider(synthetic_prices_df: pd.DataFrame) -> None:
    df = synthetic_prices_df.copy()
    df["provider"] = "robinhood"  # not in allowed list
    with pytest.raises(pandera.errors.SchemaError):
        PRICES_SCHEMA.validate(df)


def test_rejects_extra_columns(synthetic_prices_df: pd.DataFrame) -> None:
    df = synthetic_prices_df.copy()
    df["dividend"] = 0.0
    # `strict=True` schema mismatches raise SchemaErrors (plural).
    with pytest.raises((pandera.errors.SchemaError, pandera.errors.SchemaErrors)):
        PRICES_SCHEMA.validate(df)
