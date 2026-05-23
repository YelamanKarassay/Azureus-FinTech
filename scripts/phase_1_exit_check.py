"""Phase 1 exit demonstration.

Phase 1 exit criterion per `docs/PHASE_1_CHECKLIST.md`:
> One-line script (or `uv run` command) queries any HSI ticker over any
> 10y range via `DataSource.get_prices(...)` and returns clean PIT-correct
> data. Verified by `AuditingDataSource` wrapper.

This is the minimal end-to-end demonstration that the data layer is
ready for Phase 2 (backtester). The `AuditingDataSource` wrapper is
used so a regression in the read path would surface immediately as a
`LookaheadError`. Note: `get_prices` itself has no PIT semantics (daily
bars report same-day), so the audit's primary correctness claim is
exercised by `tests/test_pit_regression.py`. This script demonstrates
that the read path works end-to-end through the wrap.

Run:
    uv run python -m scripts.phase_1_exit_check
    uv run python -m scripts.phase_1_exit_check --ticker 0005.HK --start 2014-01-01
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys

from azureus.data.sources.auditing import AuditingDataSource, LookaheadError
from azureus.data.sources.yfinance_source import YFinanceDataSource


def main() -> int:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="Phase 1 exit demonstration.")
    parser.add_argument("--ticker", default="0700.HK", help="Ticker to probe (default: 0700.HK)")
    parser.add_argument(
        "--start",
        default="2014-01-01",
        help="Start date in YYYY-MM-DD (default: 2014-01-01)",
    )
    args = parser.parse_args()

    start = dt.date.fromisoformat(args.start)
    end = dt.date.today()

    audit = AuditingDataSource(inner=YFinanceDataSource())

    try:
        df = audit.get_prices(
            tickers=[args.ticker],
            start=start,
            end=end,
            fields=("close", "volume"),
        )
    except LookaheadError as exc:
        print(f"FAILED — PIT violation detected: {exc}", file=sys.stderr)
        return 2

    print(f"=== Phase 1 exit check: {args.ticker} ===")
    print(f"Range:                 {start} → {end} ({(end - start).days / 365.25:.2f}y)")
    print(f"Rows returned:         {len(df)}")
    print(f"Lookahead violations:  {audit.lookahead_violations}")
    print(f"Audit fundamentals calls: {audit.fundamentals_calls}")
    if not df.empty:
        first = df["date"].min()
        last = df["date"].max()
        print(f"First bar:             {first}  close={df.iloc[0]['close']}")
        print(f"Last bar:              {last}  close={df.iloc[-1]['close']}")

    # Exit non-zero if either we got no data or the audit fired.
    if df.empty:
        print("FAILED — no rows returned. Has ingest_prices_batch run?", file=sys.stderr)
        return 1
    if audit.lookahead_violations > 0:
        return 2

    print()
    print("OK — Phase 1 data layer exit criterion met.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
