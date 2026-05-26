"""Prefect flows for Webull-backed public price ingestion."""

from __future__ import annotations

import datetime as dt
import logging
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from prefect import flow
from sqlalchemy import text

from azureus.data.sources.webull_source import (
    DEFAULT_WEBULL_START,
    PROVIDER_NAME,
    fetch_prices_from_webull,
)
from azureus.data.validators import PRICES_SCHEMA
from azureus.pipelines.ingest_prices_free import _upsert_prices
from azureus.pipelines.ingest_prices_free import _write_ingestion_run as _write_price_run
from azureus.utils.reproducibility import capture_reproducibility

logger = logging.getLogger(__name__)

_PIPELINE_NAME = "ingest_prices_webull"
_BATCH_PIPELINE_NAME = "ingest_prices_webull_batch"
_DEFAULT_CONCURRENCY = 3


def _ingest_one_webull_ticker(
    ticker: str,
    start: dt.date = DEFAULT_WEBULL_START,
    end: dt.date | None = None,
) -> dict[str, Any]:
    """Single ticker Webull fetch → validate → upsert. NEVER raises."""
    target_end = end or dt.date.today()
    started_at = dt.datetime.now(tz=dt.UTC)
    status = "running"
    rows_inserted = 0
    errors_payload: dict[str, Any] | None = None

    try:
        df = fetch_prices_from_webull(ticker, start, target_end)
        df = PRICES_SCHEMA.validate(df, lazy=False)
        rows_inserted = _upsert_prices(df)
        status = "success"
    except Exception as exc:
        status = "failed"
        errors_payload = {
            "exception_type": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exc(),
        }
        logger.exception("Webull price ingestion failed for ticker=%s", ticker)
    finally:
        _write_ingestion_run(
            started_at=started_at,
            status=status,
            rows_inserted=rows_inserted,
            errors_payload=errors_payload,
            config={
                "ticker": ticker,
                "start": start.isoformat(),
                "end": target_end.isoformat(),
                "reproducibility": capture_reproducibility(),
            },
        )

    return {
        "status": status,
        "ticker": ticker,
        "rows_inserted": rows_inserted,
        "start": start.isoformat(),
        "end": target_end.isoformat(),
        "error": errors_payload["message"] if errors_payload else None,
    }


@flow(name=_PIPELINE_NAME, log_prints=False)
def ingest_prices_webull(
    ticker: str,
    start: dt.date = DEFAULT_WEBULL_START,
    end: dt.date | None = None,
) -> dict[str, Any]:
    """Single-ticker Webull price ingestion flow."""
    result = _ingest_one_webull_ticker(ticker=ticker, start=start, end=end)
    if result["status"] == "failed":
        raise RuntimeError(f"Webull ingestion failed for ticker={ticker}")
    return result


@flow(name=_BATCH_PIPELINE_NAME, log_prints=False)
def ingest_prices_webull_batch(
    tickers: list[str] | None = None,
    start: dt.date = DEFAULT_WEBULL_START,
    end: dt.date | None = None,
    concurrency: int = _DEFAULT_CONCURRENCY,
) -> dict[str, Any]:
    """Fan out Webull price ingestion across active or explicit tickers."""
    target_tickers = tickers if tickers is not None else _load_active_tickers()
    if not target_tickers:
        return _summary({}, status="noop")

    results: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = {
            pool.submit(_ingest_one_webull_ticker, ticker, start, end): ticker
            for ticker in target_tickers
        }
        for future in as_completed(futures):
            ticker = futures[future]
            try:
                results[ticker] = future.result()
            except Exception as exc:
                logger.exception("Webull worker raised for ticker=%s", ticker)
                results[ticker] = {
                    "status": "failed",
                    "ticker": ticker,
                    "rows_inserted": 0,
                    "error": f"worker raised: {exc}",
                }

    status = _aggregate_status(results)
    if status == "failed":
        raise RuntimeError("Webull ingestion failed for all tickers")
    return _summary(results, status=status)


def main() -> None:
    """CLI entry point."""
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    parser = argparse.ArgumentParser(description="Batch-ingest Webull HK prices.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--ticker", help="One ticker, e.g. 0700.HK")
    group.add_argument("--tickers", nargs="+", help="Explicit ticker list")
    group.add_argument("--all-active", action="store_true", help="All active tickers")
    parser.add_argument("--start", type=dt.date.fromisoformat, default=DEFAULT_WEBULL_START)
    parser.add_argument("--end", type=dt.date.fromisoformat)
    parser.add_argument("--concurrency", type=int, default=_DEFAULT_CONCURRENCY)
    args = parser.parse_args()

    if args.ticker:
        result = ingest_prices_webull(args.ticker, start=args.start, end=args.end)
    else:
        tickers = None if args.all_active else args.tickers
        result = ingest_prices_webull_batch(
            tickers=tickers,
            start=args.start,
            end=args.end,
            concurrency=args.concurrency,
        )
    print(result)


def _write_ingestion_run(
    *,
    started_at: dt.datetime,
    status: str,
    rows_inserted: int,
    errors_payload: dict[str, Any] | None,
    config: dict[str, Any],
) -> None:
    """Persist Webull lineage using the shared price ingestion writer."""
    _write_price_run(
        started_at=started_at,
        status=status,
        rows_inserted=rows_inserted,
        errors_payload=errors_payload,
        config={**config, "provider": PROVIDER_NAME},
        pipeline_name=_PIPELINE_NAME,
        provider=PROVIDER_NAME,
    )


def _load_active_tickers() -> list[str]:
    from azureus.data.db import sync_session

    with sync_session() as session:
        rows = session.execute(
            text("SELECT ticker FROM tickers WHERE is_active ORDER BY ticker")
        ).all()
    return [row[0] for row in rows]


def _aggregate_status(results: dict[str, dict[str, Any]]) -> str:
    success = [ticker for ticker, result in results.items() if result.get("status") == "success"]
    failed = [ticker for ticker, result in results.items() if result.get("status") != "success"]
    if not failed:
        return "success"
    if not success:
        return "failed"
    return "partial"


def _summary(results: dict[str, dict[str, Any]], *, status: str) -> dict[str, Any]:
    failed_tickers = [
        ticker for ticker, result in results.items() if result.get("status") != "success"
    ]
    return {
        "status": status,
        "tickers_total": len(results),
        "tickers_success": len(results) - len(failed_tickers),
        "tickers_failed": len(failed_tickers),
        "failed_tickers": failed_tickers,
        "total_rows_inserted": sum(result.get("rows_inserted", 0) for result in results.values()),
    }


if __name__ == "__main__":
    main()
