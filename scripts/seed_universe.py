"""Bulk-load `universe_membership` from a CSV.

For Phase 1 free-source data (Option B per `docs/PHASE_1_CHECKLIST.md` Day 9):
- Anchor names confirmed HSI members pre-2014 use `start_date = 2014-01-01`
  as a conservative lower bound (they were definitely members by that point).
- Names added to HSI post-2014 use their HK listing date as `start_date`
  — not their exact HSI inclusion date, which we don't have authoritative
  data for without Bloomberg. The README in `azureus/data/sources/` documents
  this assumption.
- `end_date` is empty for all rows — this snapshot captures only current
  members. Names removed from HSI within the 10y window are NOT captured;
  residual survivorship bias remains and is documented.

Idempotent — re-running upserts via `ON CONFLICT` on the primary key
`(index_id, ticker, start_date)`.

Run:
    uv run python -m scripts.seed_universe
    uv run python -m scripts.seed_universe --csv path/to/other.csv

Requires `tickers` to be seeded first (FK constraint).
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import logging
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy.dialects.postgresql import insert as pg_insert

from azureus.data.db import sync_session
from azureus.data.models import UniverseMembership

logger = logging.getLogger(__name__)

DEFAULT_CSV = Path(__file__).resolve().parents[1] / "data" / "universe" / "hsi_members.csv"

_UPDATABLE_COLUMNS = ("end_date", "weight_at_entry")


def _parse_date(value: str) -> dt.date | None:
    value = value.strip()
    return dt.date.fromisoformat(value) if value else None


def _parse_decimal(value: str) -> Decimal | None:
    value = value.strip()
    return Decimal(value) if value else None


def _read_rows(csv_path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with csv_path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for raw in reader:
            start_date = _parse_date(raw["start_date"])
            if start_date is None:
                raise ValueError(
                    f"start_date is required (offending row: {raw}); "
                    "see docs/PHASE_1_CHECKLIST.md Day 9 conventions"
                )
            rows.append(
                {
                    "index_id": raw["index_id"].strip(),
                    "ticker": raw["ticker"].strip(),
                    "start_date": start_date,
                    "end_date": _parse_date(raw.get("end_date", "")),
                    "weight_at_entry": _parse_decimal(raw.get("weight_at_entry", "")),
                }
            )
    return rows


def main(csv_path: Path = DEFAULT_CSV) -> int:
    """Seed `universe_membership` from CSV; returns the row count touched."""
    rows = _read_rows(csv_path)
    if not rows:
        logger.warning("no rows in %s — nothing to seed", csv_path)
        return 0

    stmt = pg_insert(UniverseMembership).values(rows)
    update_cols = {col: getattr(stmt.excluded, col) for col in _UPDATABLE_COLUMNS}
    stmt = stmt.on_conflict_do_update(
        index_elements=["index_id", "ticker", "start_date"],
        set_=update_cols,
    )

    with sync_session() as session:
        session.execute(stmt)

    logger.info("seeded %d universe rows from %s", len(rows), csv_path)
    return len(rows)


def cli() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s")
    parser = argparse.ArgumentParser(description="Seed the universe_membership table.")
    parser.add_argument(
        "--csv",
        type=Path,
        default=DEFAULT_CSV,
        help=f"Path to CSV (default: {DEFAULT_CSV})",
    )
    args = parser.parse_args()
    n = main(args.csv)
    print(f"seeded {n} universe rows")


if __name__ == "__main__":
    cli()
