"""Batch price ingestion — fan-out over many tickers concurrently.

Reuses `_ingest_one_ticker` from `ingest_prices_free` so per-ticker
lineage rows stay uniform across single and batch invocations.

Concurrency strategy: `ThreadPoolExecutor(max_workers=concurrency)`.
yfinance is I/O-bound (HTTP + parse), Python threads suffice. Default
`concurrency=4` — empirically polite for yfinance at our universe size
(~70 names). No retries inside a run: failures surface immediately on the
per-ticker `ingestion_runs` row, and the next scheduled invocation
re-attempts. Idempotency comes from `ON CONFLICT DO UPDATE` on the
`prices` PK (no duplicate rows).

The batch flow does NOT write its own `ingestion_runs` row — the
per-ticker rows are the source of truth. Aggregate status is returned in
the flow's result dict for CLI visibility.

Run:
    uv run python -m azureus.pipelines.ingest_prices_batch --all-active
    uv run python -m azureus.pipelines.ingest_prices_batch --tickers 0700.HK 0005.HK
    uv run python -m azureus.pipelines.ingest_prices_batch --all-active --concurrency 8
"""

from __future__ import annotations

import datetime as dt
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from prefect import flow
from sqlalchemy import text

from azureus.data.db import sync_session
from azureus.pipelines.ingest_prices_free import _ingest_one_ticker

logger = logging.getLogger(__name__)

_PIPELINE_NAME = "ingest_prices_batch_free"
_DEFAULT_CONCURRENCY = 4


def _load_active_tickers() -> list[str]:
    """All `is_active = True` rows from the `tickers` table, alphabetical."""
    with sync_session() as session:
        rows = session.execute(
            text("SELECT ticker FROM tickers WHERE is_active ORDER BY ticker")
        ).all()
    return [row[0] for row in rows]


@flow(name=_PIPELINE_NAME, log_prints=False)
def ingest_prices_batch_free(
    tickers: list[str] | None = None,
    lookback_days: int = 30,
    concurrency: int = _DEFAULT_CONCURRENCY,
) -> dict[str, Any]:
    """Fan-out fetch → validate → upsert across many tickers.

    Args:
        tickers: explicit list, or `None` to load all active tickers from DB.
        lookback_days: same semantics as the single-ticker flow.
        concurrency: max parallel worker threads.

    Returns: summary dict with per-ticker outcomes. Raises only when
    *every* ticker fails (catastrophic — likely yfinance outage or
    DB connectivity issue).
    """
    started_at = dt.datetime.now(tz=dt.UTC)

    target_tickers = tickers if tickers is not None else _load_active_tickers()
    if not target_tickers:
        logger.warning("no tickers to ingest — nothing to do")
        return {
            "status": "noop",
            "tickers_total": 0,
            "tickers_success": 0,
            "tickers_failed": 0,
            "failed_tickers": [],
            "total_rows_inserted": 0,
            "elapsed_seconds": 0.0,
        }

    results: dict[str, dict[str, Any]] = {}

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = {
            pool.submit(_ingest_one_ticker, ticker, lookback_days): ticker
            for ticker in target_tickers
        }
        for fut in as_completed(futures):
            ticker = futures[fut]
            try:
                results[ticker] = fut.result()
            except Exception as exc:
                # `_ingest_one_ticker` never raises by contract; this branch
                # would only fire on a worker-thread infrastructure failure
                # (e.g. KeyboardInterrupt propagating). Capture it so the
                # batch summary stays accurate.
                logger.exception("worker raised for ticker=%s", ticker)
                results[ticker] = {
                    "status": "failed",
                    "ticker": ticker,
                    "rows_inserted": 0,
                    "error": f"worker raised: {exc}",
                }

    success_tickers = [t for t, r in results.items() if r.get("status") == "success"]
    failed_tickers = [t for t, r in results.items() if r.get("status") != "success"]
    total_rows = sum(r.get("rows_inserted", 0) for r in results.values())

    elapsed = (dt.datetime.now(tz=dt.UTC) - started_at).total_seconds()

    if not failed_tickers:
        status = "success"
    elif not success_tickers:
        status = "failed"
    else:
        status = "partial"

    summary = {
        "status": status,
        "tickers_total": len(target_tickers),
        "tickers_success": len(success_tickers),
        "tickers_failed": len(failed_tickers),
        "failed_tickers": failed_tickers,
        "total_rows_inserted": total_rows,
        "elapsed_seconds": elapsed,
    }

    logger.info(
        "batch ingest done: %d/%d success, %d failed, %d rows in %.1fs",
        len(success_tickers),
        len(target_tickers),
        len(failed_tickers),
        total_rows,
        elapsed,
    )

    if status == "failed":
        raise RuntimeError(
            f"batch ingestion failed for all {len(failed_tickers)} tickers; "
            "see ingestion_runs rows for per-ticker details"
        )

    return summary


def main() -> None:
    """CLI entry point.

    Run with:
        uv run python -m azureus.pipelines.ingest_prices_batch --all-active
        uv run python -m azureus.pipelines.ingest_prices_batch --tickers 0700.HK 0005.HK
    """
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )

    parser = argparse.ArgumentParser(description="Batch-ingest yfinance prices.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--tickers",
        nargs="+",
        help="Explicit ticker list (space-separated), e.g. --tickers 0700.HK 0005.HK",
    )
    group.add_argument(
        "--all-active",
        action="store_true",
        help="Ingest all tickers where is_active=true",
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=30,
        help="Calendar days back from today (default: 30)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=_DEFAULT_CONCURRENCY,
        help=f"Max parallel workers (default: {_DEFAULT_CONCURRENCY})",
    )
    args = parser.parse_args()

    tickers = None if args.all_active else args.tickers
    result = ingest_prices_batch_free(
        tickers=tickers,
        lookback_days=args.lookback_days,
        concurrency=args.concurrency,
    )
    print(result)


if __name__ == "__main__":
    main()
