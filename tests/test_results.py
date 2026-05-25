"""Tests for BacktestResult conversion and JSON-safe serialization."""

from __future__ import annotations

import datetime as dt

import pandas as pd

from azureus.backtesting.portfolio import Portfolio
from azureus.backtesting.results import BacktestResult
from azureus.backtesting.value_objects import ExecutedTrade


def test_backtest_result_from_empty_portfolio_is_json_safe() -> None:
    result = BacktestResult.from_portfolio(Portfolio(initial_cash=1_000_000.0), trades=[])

    payload = result.as_dict()

    assert payload["summary"]["final_value"] == 1_000_000.0
    assert payload["equity_curve"] == []
    assert payload["holdings"] == []
    assert payload["trades"] == []


def test_backtest_result_serializes_equity_holdings_and_trades() -> None:
    portfolio = Portfolio(initial_cash=1_000_000.0)
    trade = ExecutedTrade(
        ticker="0700.HK",
        executed_at=dt.date(2024, 1, 2),
        shares=100.0,
        fill_price=400.0,
        gross_notional=40_000.0,
        commission=8.0,
        stamp_duty=0.0,
        sfc_levy=1.08,
        hkex_fee=2.0,
        ccass_fee=0.8,
        slippage=0.0,
        total_cost=11.88,
        net_cash_change=-40_011.88,
    )
    portfolio.apply_executed_trade(trade)
    portfolio.record_snapshot(dt.date(2024, 1, 2))

    result = BacktestResult.from_portfolio(portfolio, trades=[trade])
    payload = result.as_dict()

    assert isinstance(result.equity_curve, pd.DataFrame)
    assert payload["equity_curve"][0]["date"] == "2024-01-02"
    assert payload["holdings"][0]["ticker"] == "0700.HK"
    assert payload["trades"][0]["executed_at"] == "2024-01-02"
    assert payload["summary"]["total_trades"] == 1
    assert payload["summary"]["total_costs"] == 11.88
