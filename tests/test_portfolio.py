"""Portfolio tests — buy/sell, mark-to-market, weights, snapshots, long-only.

Trade objects are constructed via helpers so the test bodies stay focused
on portfolio-level invariants rather than cost-component plumbing.
"""

from __future__ import annotations

import datetime as dt

import pytest

from azureus.backtesting.portfolio import LongOnlyError, Portfolio
from azureus.backtesting.value_objects import ExecutedTrade


def _buy(ticker: str, shares: float, price: float, fees: float = 0.0) -> ExecutedTrade:
    """A simple buy: positive shares; net cash change = -(notional + fees)."""
    notional = shares * price
    return ExecutedTrade(
        ticker=ticker,
        executed_at=dt.date(2024, 1, 2),
        shares=shares,
        fill_price=price,
        gross_notional=notional,
        commission=fees,
        stamp_duty=0.0,
        sfc_levy=0.0,
        hkex_fee=0.0,
        ccass_fee=0.0,
        slippage=0.0,
        total_cost=fees,
        net_cash_change=-(notional + fees),
    )


def _sell(ticker: str, shares: float, price: float, fees: float = 0.0) -> ExecutedTrade:
    """A simple sell: negative shares; net cash change = notional - fees."""
    abs_shares = abs(shares)
    notional = abs_shares * price
    return ExecutedTrade(
        ticker=ticker,
        executed_at=dt.date(2024, 1, 2),
        shares=-abs_shares,
        fill_price=price,
        gross_notional=notional,
        commission=fees,
        stamp_duty=0.0,
        sfc_levy=0.0,
        hkex_fee=0.0,
        ccass_fee=0.0,
        slippage=0.0,
        total_cost=fees,
        net_cash_change=notional - fees,
    )


# ---- construction ---------------------------------------------------------


def test_initial_state() -> None:
    p = Portfolio(initial_cash=1_000_000)
    assert p.cash == 1_000_000
    assert dict(p.holdings) == {}
    assert p.history == ()
    assert p.total_value() == 1_000_000
    assert p.weights() == {}


def test_negative_initial_cash_rejected() -> None:
    with pytest.raises(ValueError, match="initial_cash"):
        Portfolio(initial_cash=-1.0)


# ---- apply_executed_trade -------------------------------------------------


def test_buy_creates_position_and_debits_cash() -> None:
    p = Portfolio(1_000_000)
    p.apply_executed_trade(_buy("0700.HK", 100.0, 400.0, fees=10.0))
    assert p.cash == 1_000_000 - 40_010
    pos = p.holdings["0700.HK"]
    assert pos.shares == 100.0
    assert pos.last_price == 400.0
    assert pos.market_value == 40_000.0


def test_additional_buy_accumulates_shares_and_updates_last_price() -> None:
    p = Portfolio(1_000_000)
    p.apply_executed_trade(_buy("0700.HK", 100.0, 400.0))
    p.apply_executed_trade(_buy("0700.HK", 50.0, 410.0))
    pos = p.holdings["0700.HK"]
    assert pos.shares == 150.0
    assert pos.last_price == 410.0  # newest fill
    assert pos.market_value == pytest.approx(150 * 410)


def test_partial_sell_reduces_position() -> None:
    p = Portfolio(1_000_000)
    p.apply_executed_trade(_buy("0700.HK", 100.0, 400.0))
    p.apply_executed_trade(_sell("0700.HK", 30.0, 420.0))
    pos = p.holdings["0700.HK"]
    assert pos.shares == 70.0
    assert pos.last_price == 420.0


def test_full_sell_removes_position() -> None:
    p = Portfolio(1_000_000)
    p.apply_executed_trade(_buy("0700.HK", 100.0, 400.0))
    p.apply_executed_trade(_sell("0700.HK", 100.0, 420.0))
    assert "0700.HK" not in p.holdings


def test_short_sell_against_no_position_raises() -> None:
    p = Portfolio(1_000_000)
    with pytest.raises(LongOnlyError, match="0700.HK"):
        p.apply_executed_trade(_sell("0700.HK", 100.0, 400.0))


def test_oversell_existing_position_raises() -> None:
    p = Portfolio(1_000_000)
    p.apply_executed_trade(_buy("0700.HK", 100.0, 400.0))
    with pytest.raises(LongOnlyError, match="0700.HK"):
        p.apply_executed_trade(_sell("0700.HK", 150.0, 410.0))


def test_cash_unchanged_when_long_only_violation_raises() -> None:
    """Failed trades must not partially apply — atomicity."""
    p = Portfolio(1_000_000)
    initial_cash = p.cash
    with pytest.raises(LongOnlyError):
        p.apply_executed_trade(_sell("0700.HK", 100.0, 400.0))
    assert p.cash == initial_cash


# ---- mark_to_market -------------------------------------------------------


def test_mark_to_market_refreshes_all_positions() -> None:
    p = Portfolio(1_000_000)
    p.apply_executed_trade(_buy("0700.HK", 100.0, 400.0))
    p.apply_executed_trade(_buy("0005.HK", 200.0, 50.0))
    p.mark_to_market({"0700.HK": 420.0, "0005.HK": 55.0})
    assert p.holdings["0700.HK"].last_price == 420.0
    assert p.holdings["0700.HK"].market_value == pytest.approx(42_000)
    assert p.holdings["0005.HK"].last_price == 55.0
    assert p.holdings["0005.HK"].market_value == pytest.approx(11_000)


def test_mark_to_market_missing_price_raises() -> None:
    p = Portfolio(1_000_000)
    p.apply_executed_trade(_buy("0700.HK", 100.0, 400.0))
    with pytest.raises(KeyError, match="0700.HK"):
        p.mark_to_market({"0005.HK": 50.0})


def test_mark_to_market_empty_portfolio_is_noop() -> None:
    p = Portfolio(1_000_000)
    p.mark_to_market({"0700.HK": 400.0})  # ticker we don't hold — irrelevant
    assert p.cash == 1_000_000
    assert dict(p.holdings) == {}


# ---- derived state --------------------------------------------------------


def test_total_value_combines_cash_and_holdings() -> None:
    p = Portfolio(1_000_000)
    p.apply_executed_trade(_buy("0700.HK", 100.0, 400.0))
    # cash = 1_000_000 - 40_000 = 960_000; market = 40_000; total = 1_000_000
    assert p.total_value() == pytest.approx(1_000_000)


def test_weights_implicit_cash_residual() -> None:
    p = Portfolio(1_000_000)
    p.apply_executed_trade(_buy("0700.HK", 100.0, 400.0))  # 40k stock
    p.apply_executed_trade(_buy("0005.HK", 200.0, 50.0))  # 10k stock
    # cash = 950k, total = 1M → stocks total 0.05 of portfolio
    w = p.weights()
    assert w["0700.HK"] == pytest.approx(0.04)
    assert w["0005.HK"] == pytest.approx(0.01)
    assert sum(w.values()) == pytest.approx(0.05)
    assert "__CASH__" not in w


def test_weights_empty_when_total_is_zero() -> None:
    p = Portfolio(initial_cash=0.0)
    assert p.weights() == {}


# ---- snapshots + history --------------------------------------------------


def test_snapshot_captures_current_state() -> None:
    p = Portfolio(1_000_000)
    p.apply_executed_trade(_buy("0700.HK", 100.0, 400.0))
    snap = p.record_snapshot(dt.date(2024, 1, 2))
    assert snap.as_of_date == dt.date(2024, 1, 2)
    assert snap.cash == pytest.approx(960_000)
    assert snap.total_value == pytest.approx(1_000_000)
    assert snap.holdings["0700.HK"].shares == 100.0


def test_history_accumulates_in_call_order() -> None:
    p = Portfolio(1_000_000)
    p.record_snapshot(dt.date(2024, 1, 2))
    p.apply_executed_trade(_buy("0700.HK", 100.0, 400.0))
    p.record_snapshot(dt.date(2024, 1, 3))
    assert len(p.history) == 2
    assert p.history[0].holdings == {}
    assert p.history[1].holdings["0700.HK"].shares == 100.0


def test_snapshot_immutable_to_later_changes() -> None:
    """A recorded snapshot must NOT reflect mutations that happen after it."""
    p = Portfolio(1_000_000)
    p.apply_executed_trade(_buy("0700.HK", 100.0, 400.0))
    p.record_snapshot(dt.date(2024, 1, 2))
    p.apply_executed_trade(_buy("0700.HK", 50.0, 410.0))
    # Snapshot recorded with 100 shares; current state is 150.
    assert p.history[0].holdings["0700.HK"].shares == 100.0
    assert p.holdings["0700.HK"].shares == 150.0


def test_history_unaffected_by_mark_to_market() -> None:
    p = Portfolio(1_000_000)
    p.apply_executed_trade(_buy("0700.HK", 100.0, 400.0))
    p.record_snapshot(dt.date(2024, 1, 2))
    # Big price move — should not retroactively change the snapshot.
    p.mark_to_market({"0700.HK": 500.0})
    assert p.history[0].holdings["0700.HK"].last_price == 400.0
    assert p.history[0].total_value == pytest.approx(1_000_000)
    assert p.holdings["0700.HK"].last_price == 500.0
