"""Pandera schemas — validate DataFrames before they reach the database.

Every ingestion pipeline calls `SCHEMA.validate(df)` before its write step.
Failures raise `pa.errors.SchemaError` and the ingestion flow catches them,
records a `failed` row in `ingestion_runs`, and re-raises.

Schemas validate the *intermediate* pandas DataFrame shape, not the DB
storage shape. Floats here become NUMERIC(18, 6) at the DB boundary — see
CLAUDE.md "Common Mistakes" #7 (storage precision is non-negotiable; in-
memory floats are fine for the ~15 sig-digit window we care about).
"""

from __future__ import annotations

import datetime as dt

import pandas as pd
import pandera.pandas as pa

_ALLOWED_PROVIDERS = ["yfinance", "bloomberg", "akshare", "webull"]


def _high_ge_low(df: pd.DataFrame) -> bool:
    """High must be >= low whenever both are present."""
    return bool(((df["high"] >= df["low"]) | df["high"].isna() | df["low"].isna()).all())


def _no_future_dates(df: pd.DataFrame) -> bool:
    """No bars may have a date after today."""
    today = pd.Timestamp(dt.date.today())
    return bool((df["date"] <= today).all())


PRICES_SCHEMA = pa.DataFrameSchema(
    columns={
        "provider": pa.Column(str, checks=pa.Check.isin(_ALLOWED_PROVIDERS)),
        "ticker": pa.Column(str, checks=pa.Check.str_matches(r"^[0-9A-Za-z._-]+$")),
        "date": pa.Column("datetime64[ns]"),
        "open": pa.Column(float, checks=pa.Check.gt(0), nullable=True),
        "high": pa.Column(float, checks=pa.Check.gt(0), nullable=True),
        "low": pa.Column(float, checks=pa.Check.gt(0), nullable=True),
        "close": pa.Column(float, checks=pa.Check.gt(0)),
        "adjusted_close": pa.Column(float, checks=pa.Check.gt(0), nullable=True),
        "volume": pa.Column("Int64", checks=pa.Check.ge(0), nullable=True),
    },
    checks=[
        pa.Check(_high_ge_low, name="high_ge_low"),
        pa.Check(_no_future_dates, name="no_future_dates"),
    ],
    unique=["provider", "ticker", "date"],
    strict=True,
    name="PricesSchema",
)
