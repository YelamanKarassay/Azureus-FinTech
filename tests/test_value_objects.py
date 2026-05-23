"""Smoke tests for backtester value objects — frozenness, field semantics."""

from __future__ import annotations

import datetime as dt

import pytest
from pydantic import ValidationError

from azureus.backtesting.value_objects import (
    ExecutedTrade,
    PortfolioSnapshot,
    Position,
    Trade,
)


def test_trade_constructs_with_signed_shares() -> None:
    buy = Trade(ticker="0700.HK", shares=100.0, reference_price=400.0)
    sell = Trade(ticker="0700.HK", shares=-50.0, reference_price=400.0)
    assert buy.shares == 100.0
    assert sell.shares == -50.0


def test_trade_is_frozen() -> None:
    t = Trade(ticker="0700.HK", shares=100.0, reference_price=400.0)
    with pytest.raises(ValidationError):
        t.shares = 200.0  # type: ignore[misc]  -- intentional frozen-violation


def test_executed_trade_carries_all_cost_components() -> None:
    et = ExecutedTrade(
        ticker="0700.HK",
        executed_at=dt.date(2024, 1, 2),
        shares=100.0,
        fill_price=400.0,
        gross_notional=40000.0,
        commission=8.0,
        stamp_duty=0.0,
        sfc_levy=1.08,
        hkex_fee=2.0,
        ccass_fee=0.8,
        slippage=0.0,
        total_cost=11.88,
        net_cash_change=-40011.88,
    )
    assert et.gross_notional == 40000.0
    assert et.total_cost == pytest.approx(11.88)
    assert et.net_cash_change == pytest.approx(-40011.88)


def test_position_market_value_holds_caller_supplied_value() -> None:
    """We don't auto-derive `market_value` — Portfolio owns that calculation."""
    p = Position(ticker="0700.HK", shares=100.0, last_price=400.5, market_value=40050.0)
    assert p.market_value == 40050.0


def test_portfolio_snapshot_carries_holdings_map() -> None:
    snapshot = PortfolioSnapshot(
        as_of_date=dt.date(2024, 1, 2),
        cash=10_000.0,
        total_value=50_050.0,
        holdings={
            "0700.HK": Position(
                ticker="0700.HK", shares=100.0, last_price=400.5, market_value=40050.0
            ),
        },
    )
    assert snapshot.cash == 10_000.0
    assert snapshot.holdings["0700.HK"].shares == 100.0


def test_position_is_frozen() -> None:
    p = Position(ticker="0700.HK", shares=100.0, last_price=400.0, market_value=40000.0)
    with pytest.raises(ValidationError):
        p.shares = 200.0  # type: ignore[misc]  -- intentional frozen-violation
