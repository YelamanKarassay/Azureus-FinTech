"""Bulk-load the `tickers` table from a CSV.

The default CSV (`data/universe/tickers.csv`) is the v1 HSI universe per
ARCHITECTURE §1.7 — current members plus known late-additions (Meituan,
Alibaba HK, Xiaomi, JD, etc.) with documented HK listing dates. Names that
were in HSI 10 years ago but have since been removed are NOT captured;
this is a known survivorship-bias limitation of the free-source path
(see `azureus/data/sources/README.md`).

Idempotent — re-running upserts via `ON CONFLICT (ticker) DO UPDATE`.

Run:
    uv run python -m scripts.seed_tickers
    uv run python -m scripts.seed_tickers --csv path/to/other.csv
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import logging
from pathlib import Path
from typing import Any

from sqlalchemy.dialects.postgresql import insert as pg_insert

from azureus.data.db import sync_session
from azureus.data.models import Ticker

logger = logging.getLogger(__name__)

DEFAULT_CSV = Path(__file__).resolve().parents[1] / "data" / "universe" / "tickers.csv"

_UPDATABLE_COLUMNS = (
    "name",
    "exchange",
    "sector",
    "industry",
    "currency",
    "listed_date",
)


def _parse_date(value: str) -> dt.date | None:
    value = value.strip()
    return dt.date.fromisoformat(value) if value else None


def _read_rows(csv_path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with csv_path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for raw in reader:
            rows.append(
                {
                    "ticker": raw["ticker"].strip(),
                    "name": raw["name"].strip(),
                    "exchange": raw["exchange"].strip(),
                    "sector": raw["sector"].strip() or None,
                    "industry": raw["industry"].strip() or None,
                    "currency": raw["currency"].strip() or "HKD",
                    "listed_date": _parse_date(raw.get("listed_date", "")),
                }
            )
    return rows


def main(csv_path: Path = DEFAULT_CSV) -> int:
    """Seed `tickers` from CSV; returns the row count touched."""
    rows = _read_rows(csv_path)
    if not rows:
        logger.warning("no rows in %s — nothing to seed", csv_path)
        return 0

    stmt = pg_insert(Ticker).values(rows)
    update_cols = {col: getattr(stmt.excluded, col) for col in _UPDATABLE_COLUMNS}
    stmt = stmt.on_conflict_do_update(index_elements=["ticker"], set_=update_cols)

    with sync_session() as session:
        session.execute(stmt)

    logger.info("seeded %d tickers from %s", len(rows), csv_path)
    return len(rows)


def cli() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s")
    parser = argparse.ArgumentParser(description="Seed the tickers reference table.")
    parser.add_argument(
        "--csv",
        type=Path,
        default=DEFAULT_CSV,
        help=f"Path to CSV (default: {DEFAULT_CSV})",
    )
    args = parser.parse_args()
    n = main(args.csv)
    print(f"seeded {n} tickers")


if __name__ == "__main__":
    cli()
