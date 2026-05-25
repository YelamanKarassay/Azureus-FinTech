"""Ingest demo PIT fundamentals from yfinance quarterly statements.

This is the Phase 3 public/demo path. yfinance does not provide reliable
announcement timestamps for HK equities, so the fetch layer applies a
conservative 90-day reporting lag and skips rows whose proxy `reported_date`
would be in the future.
"""

from __future__ import annotations

import datetime as dt
import logging
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import pandas as pd
from prefect import flow
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from azureus.data.db import sync_session
from azureus.data.models import FundamentalPIT, IngestionRun
from azureus.data.sources.yfinance_source import (
    PROVIDER_NAME,
    fetch_fundamentals_from_yfinance,
)
from azureus.utils.reproducibility import capture_reproducibility

logger = logging.getLogger(__name__)

_PIPELINE_NAME = "ingest_fundamentals_free"
_BATCH_PIPELINE_NAME = "ingest_fundamentals_batch_free"
_TABLE_NAME = "fundamentals_pit"
_DEFAULT_CONCURRENCY = 4


def _upsert_fundamentals(df: pd.DataFrame) -> int:
    """Upsert normalized fundamentals rows into `fundamentals_pit`."""
    if df.empty:
        return 0

    records: list[dict[str, Any]] = []
    for row in df.to_dict(orient="records"):
        records.append(
            {
                "provider": row["provider"],
                "ticker": row["ticker"],
                "metric": row["metric"],
                "period_end": _as_date(row["period_end"]),
                "reported_date": _as_date(row["reported_date"]),
                "value": row["value"],
                "unit": row["unit"],
                "is_restated": bool(row["is_restated"]),
            }
        )

    stmt = pg_insert(FundamentalPIT).values(records)
    stmt = stmt.on_conflict_do_update(
        constraint="pk_fundamentals_pit",
        set_={
            "value": stmt.excluded.value,
            "unit": stmt.excluded.unit,
            "is_restated": stmt.excluded.is_restated,
        },
    )

    with sync_session() as session:
        session.execute(stmt)
    return len(records)


def _ingest_one_ticker(ticker: str) -> dict[str, Any]:
    """Single ticker fetch → normalize → upsert. NEVER raises."""
    started_at = dt.datetime.now(tz=dt.UTC)
    status = "running"
    rows_inserted = 0
    errors_payload: dict[str, Any] | None = None

    try:
        df = fetch_fundamentals_from_yfinance(ticker)
        rows_inserted = _upsert_fundamentals(df)
        status = "success"
    except Exception as exc:
        status = "failed"
        errors_payload = {
            "exception_type": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exc(),
        }
        logger.exception("fundamentals ingestion failed for ticker=%s", ticker)
    finally:
        _write_ingestion_run(
            started_at=started_at,
            status=status,
            rows_inserted=rows_inserted,
            errors_payload=errors_payload,
            config={
                "ticker": ticker,
                "reported_lag_days": 90,
                "reproducibility": capture_reproducibility(),
            },
        )

    return {
        "status": status,
        "ticker": ticker,
        "rows_inserted": rows_inserted,
        "error": errors_payload["message"] if errors_payload else None,
    }


@flow(name=_PIPELINE_NAME, log_prints=False)
def ingest_fundamentals_free(ticker: str) -> dict[str, Any]:
    """Single-ticker fundamentals flow. Raises on failure for CLI semantics."""
    result = _ingest_one_ticker(ticker)
    if result["status"] == "failed":
        raise RuntimeError(f"fundamentals ingestion failed for ticker={ticker}")
    return result


@flow(name=_BATCH_PIPELINE_NAME, log_prints=False)
def ingest_fundamentals_batch_free(
    tickers: list[str] | None = None,
    concurrency: int = _DEFAULT_CONCURRENCY,
) -> dict[str, Any]:
    """Fan out fundamentals ingestion across many tickers."""
    target_tickers = tickers if tickers is not None else _load_active_tickers()
    if not target_tickers:
        return {
            "status": "noop",
            "tickers_total": 0,
            "tickers_success": 0,
            "tickers_failed": 0,
            "failed_tickers": [],
            "total_rows_inserted": 0,
        }

    results: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = {pool.submit(_ingest_one_ticker, ticker): ticker for ticker in target_tickers}
        for future in as_completed(futures):
            ticker = futures[future]
            try:
                results[ticker] = future.result()
            except Exception as exc:
                logger.exception("fundamentals worker raised for ticker=%s", ticker)
                results[ticker] = {
                    "status": "failed",
                    "ticker": ticker,
                    "rows_inserted": 0,
                    "error": f"worker raised: {exc}",
                }

    success_tickers = [t for t, r in results.items() if r.get("status") == "success"]
    failed_tickers = [t for t, r in results.items() if r.get("status") != "success"]
    status = "success" if not failed_tickers else "failed" if not success_tickers else "partial"
    if status == "failed":
        raise RuntimeError("fundamentals ingestion failed for all tickers")

    return {
        "status": status,
        "tickers_total": len(target_tickers),
        "tickers_success": len(success_tickers),
        "tickers_failed": len(failed_tickers),
        "failed_tickers": failed_tickers,
        "total_rows_inserted": sum(r.get("rows_inserted", 0) for r in results.values()),
    }


def main() -> None:
    """CLI entry point."""
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )

    parser = argparse.ArgumentParser(description="Ingest yfinance fundamentals.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--ticker", help="One ticker, e.g. 0700.HK")
    group.add_argument("--tickers", nargs="+", help="Explicit ticker list")
    group.add_argument("--all-active", action="store_true", help="All active tickers")
    parser.add_argument("--concurrency", type=int, default=_DEFAULT_CONCURRENCY)
    args = parser.parse_args()

    if args.ticker:
        result = ingest_fundamentals_free(args.ticker)
    else:
        tickers = None if args.all_active else args.tickers
        result = ingest_fundamentals_batch_free(tickers=tickers, concurrency=args.concurrency)
    print(result)


def _load_active_tickers() -> list[str]:
    with sync_session() as session:
        rows = session.execute(
            text("SELECT ticker FROM tickers WHERE is_active ORDER BY ticker")
        ).all()
    return [row[0] for row in rows]


def _write_ingestion_run(
    *,
    started_at: dt.datetime,
    status: str,
    rows_inserted: int,
    errors_payload: dict[str, Any] | None,
    config: dict[str, Any],
) -> None:
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
            "CRITICAL: failed to persist fundamentals ingestion lineage (status=%s, rows=%d)",
            status,
            rows_inserted,
        )


def _as_date(value: object) -> dt.date:
    if isinstance(value, pd.Timestamp):
        return value.date()
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    return pd.Timestamp(str(value)).date()


if __name__ == "__main__":
    main()
