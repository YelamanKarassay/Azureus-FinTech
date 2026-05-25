"""Run Strategy 0 over the local yfinance-backed database.

Example:
    uv run python -m scripts.run_benchmark_backtest \
        --start 2014-01-01 --end 2026-05-22 --initial-capital 1000000
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

from azureus.backtesting.cost_model import HKCostModel
from azureus.backtesting.engine import BacktestConfig, BacktestEngine
from azureus.data.sources.yfinance_source import YFinanceDataSource
from azureus.strategies.benchmark import BenchmarkParams, EqualWeightedHSIBenchmark


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Phase 2 benchmark backtest.")
    parser.add_argument("--start", default="2014-01-01", help="Start date, YYYY-MM-DD")
    parser.add_argument(
        "--end",
        default=dt.date.today().isoformat(),
        help="End date, YYYY-MM-DD; defaults to today",
    )
    parser.add_argument(
        "--initial-capital",
        type=float,
        default=1_000_000.0,
        help="Initial capital in HKD",
    )
    parser.add_argument("--universe", default="HSI", help="Universe id, default HSI")
    parser.add_argument("--output-json", type=Path, help="Optional path for result JSON")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    start = dt.date.fromisoformat(args.start)
    end = dt.date.fromisoformat(args.end)
    if start > end:
        print("FAILED — start must be <= end", file=sys.stderr)
        return 2

    data_source = YFinanceDataSource()
    params = BenchmarkParams(universe_id=args.universe)
    strategy = EqualWeightedHSIBenchmark(params=params, data=data_source)
    engine = BacktestEngine(
        strategy=strategy,
        data_source=data_source,
        cost_model=HKCostModel(),
        config=BacktestConfig(
            start=start,
            end=end,
            initial_capital=args.initial_capital,
            universe_id=args.universe,
        ),
    )

    result = engine.run()
    summary = result.summary

    print("=== Phase 2 Benchmark Backtest ===")
    print(f"Strategy:       {strategy.name}")
    print(f"Universe:       {args.universe}")
    print(f"Range:          {start} -> {end}")
    print(f"Initial value:  {summary['initial_value']:.2f}")
    print(f"Final value:    {summary['final_value']:.2f}")
    print(f"Total return:   {summary['total_return']:.2%}")
    print(f"Ann. return:    {summary['annualized_return']:.2%}")
    print(f"Ann. vol:       {summary['annualized_vol']:.2%}")
    print(f"Sharpe:         {summary['sharpe']:.2f}")
    print(f"Max drawdown:   {summary['max_drawdown']:.2%}")
    print(f"DD duration:    {summary['max_drawdown_duration_days']} days")
    print(f"Total trades:   {summary['total_trades']}")
    print(f"Total costs:    {summary['total_costs']:.2f}")

    if args.output_json:
        args.output_json.write_text(json.dumps(result.as_dict(), indent=2), encoding="utf-8")
        print(f"Wrote JSON:     {args.output_json}")

    if result.equity_curve.empty:
        print("FAILED — no equity-curve rows. Has Phase 1 data been loaded?", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
