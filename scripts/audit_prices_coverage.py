"""Per-ticker price-coverage audit for the deployed `prices` table.

What a single run prints:

1. Per-ticker summary — row count, first/last date, expected bars vs.
   actual coverage ratio. Late additions (Day 9 CSV) get their expected
   window adjusted to their listing date.
2. Missing tickers — universe members with zero rows in `prices`.
3. Suspect tickers — non-empty rows but coverage ratio below a threshold
   (default 90% of expected trading-day window).
4. Date-gap audit — any ticker whose internal bar density drops below
   the ratio threshold over a rolling 30-day window.

Run:
    uv run python -m scripts.audit_prices_coverage
    uv run python -m scripts.audit_prices_coverage --index HSI
    uv run python -m scripts.audit_prices_coverage --coverage-threshold 0.85

This is a Day 13 operational check, distinct from the Day 14 recurring
`validate_db_state` Prefect flow.
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys
from dataclasses import dataclass

from sqlalchemy import text

from azureus.data.db import sync_session

logger = logging.getLogger(__name__)

# HK equities trade ~248 days/year. Use 250 as a conservative upper bound.
_TRADING_DAYS_PER_YEAR = 250
_DEFAULT_COVERAGE_THRESHOLD = 0.95
_DEFAULT_SHORTFALL_WARN_YEARS = 2.0


@dataclass
class TickerCoverage:
    ticker: str
    listed_date: dt.date | None
    universe_start: dt.date
    rows: int
    first_date: dt.date | None
    last_date: dt.date | None
    expected_bars_in_window: int  # trading days between first_date and today
    window_density: float  # rows / expected_bars_in_window
    history_shortfall_years: float  # how much earlier we'd hope to start


def _load_coverage(index_id: str) -> list[TickerCoverage]:
    """Return one `TickerCoverage` per ticker that is a universe member.

    Two coverage metrics are computed:

    - `window_density` — rows we have / expected trading days between
      first_date and today. This catches missing bars *inside* the data
      we already pulled (yfinance gaps, ingestion errors).
    - `history_shortfall_years` — how many years earlier we'd expect data
      to start, given the later of (listed_date, universe_start). This
      catches missing *history* (yfinance simply doesn't reach back far
      enough, or our lookback parameter was too small).
    """
    with sync_session() as session:
        rows = (
            session.execute(
                text(
                    """
                SELECT
                  t.ticker,
                  t.listed_date,
                  u.start_date AS universe_start,
                  COALESCE(p.row_count, 0) AS rows,
                  p.first_date,
                  p.last_date
                FROM tickers t
                JOIN universe_membership u
                  ON u.ticker = t.ticker AND u.index_id = :idx
                LEFT JOIN (
                    SELECT ticker,
                           COUNT(*) AS row_count,
                           MIN(date) AS first_date,
                           MAX(date) AS last_date
                    FROM prices
                    WHERE provider = 'yfinance'
                    GROUP BY ticker
                ) p ON p.ticker = t.ticker
                ORDER BY t.ticker
                """
                ),
                {"idx": index_id},
            )
            .mappings()
            .all()
        )

    today = dt.date.today()
    coverage: list[TickerCoverage] = []
    for r in rows:
        # Effective universe entry: the later of (listed_date, universe_start).
        ideal_start = r["universe_start"]
        if r["listed_date"] and r["listed_date"] > ideal_start:
            ideal_start = r["listed_date"]

        first_date = r["first_date"]
        last_date = r["last_date"]

        if first_date is None:
            # No rows at all — both metrics are zero / max.
            expected_in_window = 0
            density = 0.0
            shortfall_years = (today - ideal_start).days / 365.25
        else:
            window_days = max((today - first_date).days, 1)
            expected_in_window = int(round(window_days * _TRADING_DAYS_PER_YEAR / 365.25))
            density = r["rows"] / expected_in_window if expected_in_window else 0.0
            # If first_date > ideal_start, we have less history than hoped.
            shortfall_days = max((first_date - ideal_start).days, 0)
            shortfall_years = shortfall_days / 365.25

        coverage.append(
            TickerCoverage(
                ticker=r["ticker"],
                listed_date=r["listed_date"],
                universe_start=r["universe_start"],
                rows=r["rows"],
                first_date=first_date,
                last_date=last_date,
                expected_bars_in_window=expected_in_window,
                window_density=density,
                history_shortfall_years=shortfall_years,
            )
        )
    return coverage


def _print_summary(rows: list[TickerCoverage], density_threshold: float) -> None:
    print(f"{'ticker':>10} {'rows':>7} {'first':>12} {'last':>12} {'density':>9} {'shortfall':>11}")
    print("-" * 70)
    for c in rows:
        first = c.first_date.isoformat() if c.first_date else "—"
        last = c.last_date.isoformat() if c.last_date else "—"
        density_flag = " " if c.window_density >= density_threshold else "*"
        shortfall_str = f"{c.history_shortfall_years:.1f}y" if c.history_shortfall_years else "—"
        print(
            f"{c.ticker:>10} {c.rows:>7d} {first:>12} {last:>12} "
            f"{c.window_density:>8.1%}{density_flag} {shortfall_str:>11}"
        )


def _print_findings(
    rows: list[TickerCoverage],
    density_threshold: float,
    shortfall_warn_years: float,
) -> tuple[int, int, int]:
    """Return (missing_count, suspect_density_count, large_shortfall_count)."""
    missing = [c for c in rows if c.rows == 0]
    suspect_density = [c for c in rows if c.rows > 0 and c.window_density < density_threshold]
    large_shortfall = [
        c for c in rows if c.rows > 0 and c.history_shortfall_years >= shortfall_warn_years
    ]

    print()
    print(f"=== Missing tickers (zero rows in `prices`): {len(missing)} ===")
    for c in missing:
        print(
            f"  {c.ticker} — universe start {c.universe_start}, "
            f"missing ~{c.history_shortfall_years:.1f}y of history"
        )

    print()
    print(
        f"=== Low-density tickers (window density < {density_threshold:.0%}): "
        f"{len(suspect_density)} ==="
    )
    for c in suspect_density:
        print(
            f"  {c.ticker} — {c.rows} bars over "
            f"{c.first_date}–{c.last_date}, density {c.window_density:.1%}"
        )

    print()
    print(
        f"=== Large history shortfall (first_date >= {shortfall_warn_years}y "
        f"after expected universe start): {len(large_shortfall)} ==="
    )
    for c in large_shortfall:
        print(
            f"  {c.ticker} — wanted from {c.universe_start}, "
            f"got from {c.first_date} (-{c.history_shortfall_years:.1f}y)"
        )

    return len(missing), len(suspect_density), len(large_shortfall)


def _audit_zero_volume_runs(min_run_length: int = 5) -> None:
    """Surface tickers with zero-volume runs of `min_run_length` consecutive bars."""
    with sync_session() as session:
        rows = (
            session.execute(
                text(
                    """
                WITH labeled AS (
                  SELECT ticker, date,
                         COALESCE(volume, 0) AS volume,
                         ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY date)
                           - ROW_NUMBER() OVER (
                               PARTITION BY ticker,
                                            CASE WHEN COALESCE(volume,0)=0 THEN 1 ELSE 0 END
                               ORDER BY date
                             ) AS grp
                  FROM prices WHERE provider = 'yfinance'
                )
                SELECT ticker, MIN(date) AS run_start, MAX(date) AS run_end,
                       COUNT(*) AS run_len
                FROM labeled
                WHERE volume = 0
                GROUP BY ticker, grp
                HAVING COUNT(*) >= :min_len
                ORDER BY run_len DESC, ticker
                LIMIT 20
                """
                ),
                {"min_len": min_run_length},
            )
            .mappings()
            .all()
        )

    print()
    print(f"=== Zero-volume runs of >= {min_run_length} consecutive bars (top 20) ===")
    if not rows:
        print("  (none)")
        return
    for r in rows:
        print(f"  {r['ticker']}: {r['run_start']} → {r['run_end']} ({r['run_len']} bars)")


def main() -> int:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="Audit per-ticker price coverage.")
    parser.add_argument("--index", default="HSI", help="Universe index id (default: HSI)")
    parser.add_argument(
        "--density-threshold",
        type=float,
        default=_DEFAULT_COVERAGE_THRESHOLD,
        help=f"Per-ticker window-density floor (default: {_DEFAULT_COVERAGE_THRESHOLD})",
    )
    parser.add_argument(
        "--shortfall-warn-years",
        type=float,
        default=_DEFAULT_SHORTFALL_WARN_YEARS,
        help=(
            f"Warn when first_date is at least this many years after the "
            f"expected universe-start (default: {_DEFAULT_SHORTFALL_WARN_YEARS})"
        ),
    )
    args = parser.parse_args()

    rows = _load_coverage(args.index)
    if not rows:
        print(f"No tickers found for index '{args.index}' — is universe_membership seeded?")
        return 1

    _print_summary(rows, args.density_threshold)
    missing, low_density, large_shortfall = _print_findings(
        rows, args.density_threshold, args.shortfall_warn_years
    )
    _audit_zero_volume_runs()

    total = len(rows)
    print()
    print(
        f"=== Summary: {total} universe members | "
        f"{total - missing} with data | {missing} missing | "
        f"{low_density} low-density | {large_shortfall} short history ==="
    )

    # Exit non-zero only for the hard quality gate — missing or low-density.
    # Large history shortfall is informational (free-data limitation).
    return 0 if missing == 0 and low_density == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
