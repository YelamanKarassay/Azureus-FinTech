"""Refresh ticker metadata from yfinance.

Phase 1 scope: refresh `name` only. The CSV (`data/universe/tickers.csv`)
is the authoritative source for `sector` / `industry` / `currency`; this
flow does NOT touch those columns. The Bloomberg path (Phase 5) replaces
yfinance metadata wholesale with `INDX_MWEIGHT_HIST`-derived data.

Failures per ticker (yfinance returns no resolvable data) are collected
into the lineage row's `errors` JSONB, not raised — one ticker's quirk
shouldn't abort a maintenance refresh of 69 names.

Run:
    uv run python -m azureus.pipelines.ingest_tickers_free
    uv run python -m azureus.pipelines.ingest_tickers_free --tickers 0700.HK

Cadence: weekly (per `docs/PHASE_1_CHECKLIST.md`). Phase 1 invokes the
flow manually; Phase 2 brings the Prefect server and scheduling.
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Any

import yfinance as yf
from prefect import flow
from sqlalchemy import select, text

from azureus.data.db import sync_session
from azureus.data.models import IngestionRun, Ticker
from azureus.data.sources.yfinance_source import PROVIDER_NAME
from azureus.utils.reproducibility import capture_reproducibility

logger = logging.getLogger(__name__)

_PIPELINE_NAME = "ingest_tickers_free"
_TABLE_NAME = "tickers"


def _resolve_name(ticker: str) -> str | None:
    """Fetch a usable display name for `ticker` from yfinance, or `None`.

    yfinance HK coverage of `info` is spotty; we accept either field and
    return `None` when neither is available so the caller can record the
    failure cleanly.
    """
    info = yf.Ticker(ticker).info
    return info.get("shortName") or info.get("longName") or None


@flow(name=_PIPELINE_NAME, log_prints=False)
def ingest_tickers_free(tickers: list[str] | None = None) -> dict[str, Any]:
    """Refresh `tickers.name` from yfinance for the given (or all active) tickers.

    Writes one `ingestion_runs` row per invocation summarising the batch.
    """
    started_at = dt.datetime.now(tz=dt.UTC)

    if tickers is None:
        with sync_session() as session:
            target_tickers = [
                row[0]
                for row in session.execute(
                    text("SELECT ticker FROM tickers WHERE is_active ORDER BY ticker")
                ).all()
            ]
    else:
        target_tickers = list(tickers)

    rows_updated = 0
    rows_failed = 0
    errors: list[dict[str, str]] = []

    for ticker in target_tickers:
        try:
            new_name = _resolve_name(ticker)
        except Exception as exc:
            rows_failed += 1
            errors.append({"ticker": ticker, "reason": f"{type(exc).__name__}: {exc}"})
            logger.warning("yfinance lookup failed for %s: %s", ticker, exc)
            continue

        if not new_name:
            rows_failed += 1
            errors.append({"ticker": ticker, "reason": "no name from yfinance"})
            logger.warning("yfinance returned no name for %s", ticker)
            continue

        with sync_session() as session:
            current = session.execute(
                select(Ticker).where(Ticker.ticker == ticker)
            ).scalar_one_or_none()
            if current is not None and current.name != new_name:
                current.name = new_name
                rows_updated += 1

    status = "success" if rows_failed == 0 else "partial"

    summary = {
        "status": status,
        "tickers_total": len(target_tickers),
        "rows_updated": rows_updated,
        "rows_failed": rows_failed,
    }

    _write_ingestion_run(
        started_at=started_at,
        status=status,
        rows_updated=rows_updated,
        rows_failed=rows_failed,
        errors=errors,
        config={
            "tickers_total": len(target_tickers),
            "scope": "all_active" if tickers is None else "explicit",
            "reproducibility": capture_reproducibility(),
        },
    )

    logger.info(
        "ticker refresh done: %d updated, %d failed, %d total",
        rows_updated,
        rows_failed,
        len(target_tickers),
    )
    return summary


def _write_ingestion_run(
    *,
    started_at: dt.datetime,
    status: str,
    rows_updated: int,
    rows_failed: int,
    errors: list[dict[str, str]],
    config: dict[str, Any],
) -> None:
    """Persist the run's lineage row. Best-effort; logs loudly on failure."""
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
                    rows_inserted=0,
                    rows_updated=rows_updated,
                    rows_failed=rows_failed,
                    errors={"failures": errors} if errors else None,
                    config=config,
                )
            )
    except Exception:
        logger.exception(
            "CRITICAL: failed to persist ingestion_runs row "
            "(status=%s, updated=%d, failed=%d) — lineage is incomplete",
            status,
            rows_updated,
            rows_failed,
        )


def main() -> None:
    """CLI entry."""
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )

    parser = argparse.ArgumentParser(description="Refresh ticker metadata from yfinance.")
    parser.add_argument(
        "--tickers",
        nargs="+",
        default=None,
        help="Specific tickers; default: all active tickers in DB",
    )
    args = parser.parse_args()

    result = ingest_tickers_free(tickers=args.tickers)
    print(result)


if __name__ == "__main__":
    main()
