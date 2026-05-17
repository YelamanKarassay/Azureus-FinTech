"""Prefect flow — ingest daily OHLCV for a single ticker via yfinance.

In-process Prefect 3: tasks run synchronously, no server needed. The
Prefect server container is deferred to Phase 2 (`docs/ARCHITECTURE.md`
§3.7). Decorators stay so the deferral is a config change, not a rewrite.

Every flow run writes exactly one `ingestion_runs` row, success or fail.
"No silent swallows" per CLAUDE.md "Common Mistakes" #9.
"""

from __future__ import annotations

import datetime as dt
import logging
import traceback
from typing import Any

import pandas as pd
from prefect import flow, task
from sqlalchemy.dialects.postgresql import insert as pg_insert

from azureus.data.db import sync_session
from azureus.data.models import IngestionRun, Price
from azureus.data.sources.yfinance_source import (
    PROVIDER_NAME,
    fetch_prices_from_yfinance,
)
from azureus.data.validators import PRICES_SCHEMA
from azureus.utils.reproducibility import capture_reproducibility

logger = logging.getLogger(__name__)

_PIPELINE_NAME = "ingest_prices_free"
_TABLE_NAME = "prices"
_UPDATABLE_COLUMNS = (
    "open",
    "high",
    "low",
    "close",
    "adjusted_close",
    "volume",
)


@task(name="fetch_prices")
def fetch_prices(ticker: str, start: dt.date, end: dt.date) -> pd.DataFrame:
    return fetch_prices_from_yfinance(ticker, start, end)


@task(name="validate_prices")
def validate_prices(df: pd.DataFrame) -> pd.DataFrame:
    return PRICES_SCHEMA.validate(df, lazy=False)


@task(name="upsert_prices")
def upsert_prices(df: pd.DataFrame) -> int:
    """Upsert one batch into `prices`. Returns row count touched.

    `INSERT ... ON CONFLICT (provider, ticker, date) DO UPDATE` —
    idempotent under re-ingestion (per ARCHITECTURE §3.7).
    """
    if df.empty:
        return 0

    records: list[dict[str, Any]] = []
    for row in df.to_dict(orient="records"):
        date_value = row["date"]
        if isinstance(date_value, pd.Timestamp):
            date_value = date_value.date()
        records.append(
            {
                "provider": row["provider"],
                "ticker": row["ticker"],
                "date": date_value,
                "open": row["open"],
                "high": row["high"],
                "low": row["low"],
                "close": row["close"],
                "adjusted_close": row["adjusted_close"],
                "volume": (int(row["volume"]) if pd.notna(row["volume"]) else None),
            }
        )

    stmt = pg_insert(Price).values(records)
    update_cols = {col: getattr(stmt.excluded, col) for col in _UPDATABLE_COLUMNS}
    stmt = stmt.on_conflict_do_update(constraint="pk_prices", set_=update_cols)

    with sync_session() as session:
        session.execute(stmt)
    return len(records)


@flow(name=_PIPELINE_NAME, log_prints=False)
def ingest_prices_free(ticker: str, lookback_days: int = 30) -> dict[str, Any]:
    """Fetch → validate → upsert prices for one ticker.

    Writes exactly one `ingestion_runs` row per call. On failure, the row is
    persisted with `status='failed'` and full exception context, then the
    error is re-raised.
    """
    end = dt.date.today()
    start = end - dt.timedelta(days=lookback_days)
    started_at = dt.datetime.now(tz=dt.UTC)

    status = "running"
    rows_inserted = 0
    errors_payload: dict[str, Any] | None = None

    try:
        df = fetch_prices(ticker, start, end)
        df = validate_prices(df)
        rows_inserted = upsert_prices(df)
        status = "success"
    except Exception as exc:
        status = "failed"
        errors_payload = {
            "exception_type": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exc(),
        }
        logger.exception("ingestion failed for ticker=%s", ticker)
        # Re-raised after lineage write below.
    finally:
        _write_ingestion_run(
            started_at=started_at,
            status=status,
            rows_inserted=rows_inserted,
            errors_payload=errors_payload,
            config={
                "ticker": ticker,
                "start": start.isoformat(),
                "end": end.isoformat(),
                "lookback_days": lookback_days,
                "reproducibility": capture_reproducibility(),
            },
        )

    if status == "failed":
        raise RuntimeError(f"ingestion failed for ticker={ticker}; see ingestion_runs row")

    return {
        "status": status,
        "ticker": ticker,
        "rows_inserted": rows_inserted,
        "start": start.isoformat(),
        "end": end.isoformat(),
    }


def main() -> None:
    """CLI entry point.

    Run with: `uv run python -m azureus.pipelines.ingest_prices_free --ticker 0700.HK`
    """
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )

    parser = argparse.ArgumentParser(description="Ingest yfinance prices for one ticker.")
    parser.add_argument("--ticker", required=True, help="yfinance ticker, e.g. 0700.HK")
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=30,
        help="Number of calendar days back from today (default: 30)",
    )
    args = parser.parse_args()

    result = ingest_prices_free(ticker=args.ticker, lookback_days=args.lookback_days)
    print(result)


def _write_ingestion_run(
    *,
    started_at: dt.datetime,
    status: str,
    rows_inserted: int,
    errors_payload: dict[str, Any] | None,
    config: dict[str, Any],
) -> None:
    """Persist a lineage row. Log loudly if even *this* fails (no silent swallows)."""
    try:
        with sync_session() as session:
            session.add(
                IngestionRun(
                    pipeline_name=_PIPELINE_NAME,
                    provider=PROVIDER_NAME,
                    table_name=_TABLE_NAME,
                    status=status,
                    started_at=started_at,
                    completed_at=dt.datetime.now(tz=dt.UTC),
                    rows_inserted=rows_inserted,
                    rows_updated=0,
                    rows_failed=0,
                    errors=errors_payload,
                    config=config,
                )
            )
    except Exception:
        logger.exception(
            "CRITICAL: failed to persist ingestion_runs row "
            "(status=%s, rows=%d) — lineage is incomplete",
            status,
            rows_inserted,
        )


if __name__ == "__main__":
    main()
