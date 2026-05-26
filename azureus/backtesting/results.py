"""Backtest result container and Portfolio-to-analytics conversion."""

from __future__ import annotations

import datetime as dt
import math
from typing import Any, cast

import pandas as pd
from pydantic import BaseModel, ConfigDict

from azureus.backtesting import metrics
from azureus.backtesting.portfolio import Portfolio
from azureus.backtesting.value_objects import ExecutedTrade


class BacktestResult(BaseModel):
    """API-ready backtest output: summary scalars plus chart DataFrames."""

    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

    summary: dict[str, float | int | str | None]
    equity_curve: pd.DataFrame
    holdings: pd.DataFrame
    trades: pd.DataFrame
    diagnostics: dict[str, Any] | None = None

    @classmethod
    def from_portfolio(
        cls,
        portfolio: Portfolio,
        trades: list[ExecutedTrade],
    ) -> BacktestResult:
        """Build result DataFrames and summary metrics from a completed portfolio."""
        equity_curve = _equity_curve_from_portfolio(portfolio)
        holdings = _holdings_from_portfolio(portfolio)
        trades_df = _trades_frame(trades)
        summary = _summary_from_frames(portfolio, equity_curve, trades_df, holdings)
        return cls(
            summary=summary,
            equity_curve=equity_curve,
            holdings=holdings,
            trades=trades_df,
        )

    def as_dict(self) -> dict[str, Any]:
        """JSONB-serializable representation for `backtest_results` persistence."""
        return {
            "summary": _json_safe_mapping(self.summary),
            "equity_curve": _frame_records(self.equity_curve),
            "holdings": _frame_records(self.holdings),
            "trades": _frame_records(self.trades),
            "diagnostics": _json_safe_value(self.diagnostics),
        }


def _equity_curve_from_portfolio(portfolio: Portfolio) -> pd.DataFrame:
    rows = [
        {
            "date": snap.as_of_date,
            "cash": snap.cash,
            "total_value": snap.total_value,
        }
        for snap in portfolio.history
    ]
    df = pd.DataFrame(rows, columns=["date", "cash", "total_value"])
    if df.empty:
        df["daily_return"] = pd.Series(dtype=float)
        return df
    df["daily_return"] = df["total_value"].pct_change()
    if portfolio.initial_cash > 0:
        df.loc[df.index[0], "daily_return"] = (
            df.loc[df.index[0], "total_value"] / (portfolio.initial_cash) - 1.0
        )
    else:
        df.loc[df.index[0], "daily_return"] = 0.0
    df["daily_return"] = df["daily_return"].fillna(0.0)
    return df


def _holdings_from_portfolio(portfolio: Portfolio) -> pd.DataFrame:
    rows: list[dict[str, float | str | dt.date]] = []
    for snap in portfolio.history:
        for ticker, position in snap.holdings.items():
            weight = position.market_value / snap.total_value if snap.total_value > 0 else 0.0
            rows.append(
                {
                    "date": snap.as_of_date,
                    "ticker": ticker,
                    "weight": weight,
                    "shares": position.shares,
                    "last_price": position.last_price,
                    "market_value": position.market_value,
                }
            )
    return pd.DataFrame(
        rows,
        columns=["date", "ticker", "weight", "shares", "last_price", "market_value"],
    )


def _trades_frame(trades: list[ExecutedTrade]) -> pd.DataFrame:
    rows = [trade.model_dump() for trade in trades]
    return pd.DataFrame(
        rows,
        columns=[
            "ticker",
            "executed_at",
            "shares",
            "fill_price",
            "gross_notional",
            "commission",
            "stamp_duty",
            "sfc_levy",
            "hkex_fee",
            "ccass_fee",
            "slippage",
            "total_cost",
            "net_cash_change",
        ],
    )


def _summary_from_frames(
    portfolio: Portfolio,
    equity_curve: pd.DataFrame,
    trades: pd.DataFrame,
    holdings: pd.DataFrame,
) -> dict[str, float | int | str | None]:
    if equity_curve.empty:
        return {
            "start_date": None,
            "end_date": None,
            "initial_value": portfolio.initial_cash,
            "final_value": portfolio.cash,
            "final_cash": portfolio.cash,
            "total_return": 0.0,
            "annualized_return": math.nan,
            "annualized_vol": 0.0,
            "sharpe": math.nan,
            "sortino": math.nan,
            "calmar": math.nan,
            "max_drawdown": 0.0,
            "max_drawdown_duration_days": 0,
            "total_trades": 0,
            "total_costs": 0.0,
            "cost_drag": 0.0,
            "avg_holdings": 0.0,
        }

    equity = equity_curve.set_index("date")["total_value"]
    returns = equity_curve.set_index("date")["daily_return"]
    initial_value = portfolio.initial_cash
    final_value = float(equity.iloc[-1])
    ann_return = metrics.annualized_return(returns)
    max_dd, _peak, _trough, _recovery, dd_duration = metrics.max_drawdown_with_duration(equity)
    total_costs = float(trades["total_cost"].sum()) if not trades.empty else 0.0
    avg_holdings = 0.0
    if not holdings.empty:
        holdings_per_day = holdings.groupby("date")["ticker"].nunique()
        avg_holdings = float(holdings_per_day.mean())

    return {
        "start_date": str(equity_curve["date"].iloc[0]),
        "end_date": str(equity_curve["date"].iloc[-1]),
        "initial_value": initial_value,
        "final_value": final_value,
        "final_cash": float(equity_curve["cash"].iloc[-1]),
        "total_return": final_value / initial_value - 1.0 if initial_value > 0 else math.nan,
        "annualized_return": ann_return,
        "annualized_vol": metrics.annualized_vol(returns),
        "sharpe": metrics.sharpe(returns),
        "sortino": metrics.sortino(returns),
        "calmar": metrics.calmar(ann_return, max_dd),
        "max_drawdown": max_dd,
        "max_drawdown_duration_days": dd_duration,
        "total_trades": int(len(trades)),
        "total_costs": total_costs,
        "cost_drag": total_costs / initial_value if initial_value > 0 else math.nan,
        "avg_holdings": avg_holdings,
    }


def _json_safe_value(value: Any) -> Any:
    if isinstance(value, pd.Timestamp):
        return value.date().isoformat()
    if isinstance(value, dt.datetime):
        return value.isoformat()
    if isinstance(value, dt.date):
        return value.isoformat()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {key: _json_safe_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe_value(item) for item in value]
    return value


def _json_safe_mapping(mapping: dict[str, Any]) -> dict[str, Any]:
    return {key: _json_safe_value(value) for key, value in mapping.items()}


def _frame_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for row in df.to_dict(orient="records"):
        records.append(_json_safe_mapping(cast(dict[str, Any], row)))
    return records
