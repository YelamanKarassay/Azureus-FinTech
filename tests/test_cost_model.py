"""HKCostModel tests — the CLAUDE.md-required cost-model assertions.

Per CLAUDE.md "Required tests": *any change to fees must include a test
asserting expected bps on a known trade.* The first few tests below are
the canonical assertions; the rest cover slippage scaling, asymmetry,
input validation, and overrides.
"""

from __future__ import annotations

import datetime as dt

import pytest

from azureus.backtesting.cost_model import HKCostModel
from azureus.backtesting.value_objects import Trade

# Standard probe: 100 shares × HK$400 = HK$40,000 notional.
_TEST_DATE = dt.date(2024, 1, 2)
_LIQUID_MDV = 1_000_000_000  # large enough that slippage is negligible


def _buy() -> Trade:
    return Trade(ticker="0700.HK", shares=100.0, reference_price=400.0)


def _sell() -> Trade:
    return Trade(ticker="0700.HK", shares=-100.0, reference_price=400.0)


# ---- canonical fee assertions (CLAUDE.md required) ----------------------


def test_buy_side_fees_match_expected_bps() -> None:
    """2.97 bps per side × HK$40k notional = HK$11.88 (excl. tiny slippage)."""
    et = HKCostModel().execute(_buy(), 400.0, _LIQUID_MDV, _TEST_DATE)
    fees_no_slippage = et.commission + et.stamp_duty + et.sfc_levy + et.hkex_fee + et.ccass_fee
    assert fees_no_slippage == pytest.approx(11.88)
    assert et.commission == pytest.approx(8.00)
    assert et.stamp_duty == 0.0  # no stamp duty on the buy side
    assert et.sfc_levy == pytest.approx(1.08)
    assert et.hkex_fee == pytest.approx(2.00)
    assert et.ccass_fee == pytest.approx(0.80)


def test_sell_side_fees_match_expected_bps() -> None:
    """12.97 bps per side × HK$40k notional = HK$51.88 (excl. slippage)."""
    et = HKCostModel().execute(_sell(), 400.0, _LIQUID_MDV, _TEST_DATE)
    fees_no_slippage = et.commission + et.stamp_duty + et.sfc_levy + et.hkex_fee + et.ccass_fee
    assert fees_no_slippage == pytest.approx(51.88)
    assert et.stamp_duty == pytest.approx(40.00)  # the asymmetric fee


def test_round_trip_total_about_16_bps() -> None:
    """Round-trip on a 40k trade ≈ 15.94 bps ≈ HK$63.76 in fees."""
    cm = HKCostModel()
    buy = cm.execute(_buy(), 400.0, _LIQUID_MDV, _TEST_DATE)
    sell = cm.execute(_sell(), 400.0, _LIQUID_MDV, _TEST_DATE)

    fees_per_side = lambda et: (  # noqa: E731
        et.commission + et.stamp_duty + et.sfc_levy + et.hkex_fee + et.ccass_fee
    )
    round_trip = fees_per_side(buy) + fees_per_side(sell)
    assert round_trip == pytest.approx(63.76, abs=0.01)

    bps_round_trip = round_trip / 40_000 * 10_000
    assert bps_round_trip == pytest.approx(15.94, abs=0.01)


def test_sell_side_exceeds_buy_side_by_exactly_stamp_duty() -> None:
    """The asymmetry IS the stamp duty — nothing else differs between sides."""
    cm = HKCostModel()
    buy = cm.execute(_buy(), 400.0, _LIQUID_MDV, _TEST_DATE)
    sell = cm.execute(_sell(), 400.0, _LIQUID_MDV, _TEST_DATE)

    fees_per_side = lambda et: (  # noqa: E731
        et.commission + et.stamp_duty + et.sfc_levy + et.hkex_fee + et.ccass_fee
    )
    assert fees_per_side(sell) - fees_per_side(buy) == pytest.approx(sell.stamp_duty)


# ---- slippage scaling ---------------------------------------------------


def test_slippage_scales_with_sqrt_of_volume_ratio() -> None:
    """slippage_bps = α × (notional/MDV)^0.5 — quadruple the ratio, 2× the slip."""
    cm = HKCostModel(
        commission_bps=0,
        stamp_duty_bps=0,
        sfc_levy_bps=0,
        hkex_fee_bps=0,
        ccass_fee_bps=0,
    )
    trade = Trade(ticker="X.HK", shares=100.0, reference_price=100.0)  # 10k notional
    e1 = cm.execute(trade, 100.0, 1_000_000, _TEST_DATE)  # notional/MDV = 0.01
    e2 = cm.execute(trade, 100.0, 250_000, _TEST_DATE)  # notional/MDV = 0.04 (4×)

    assert e2.slippage == pytest.approx(2.0 * e1.slippage, rel=1e-9)


def test_slippage_formula_matches_known_value() -> None:
    """For a HK$10k trade on MDV HK$1M: slippage = 1.0 bps = HK$1.00."""
    cm = HKCostModel(
        commission_bps=0,
        stamp_duty_bps=0,
        sfc_levy_bps=0,
        hkex_fee_bps=0,
        ccass_fee_bps=0,
    )
    trade = Trade(ticker="X.HK", shares=100.0, reference_price=100.0)
    et = cm.execute(trade, 100.0, 1_000_000, _TEST_DATE)
    # slippage_bps = 10 * (10000/1000000)^0.5 = 10 * 0.1 = 1.0
    # slippage_$ = 10000 * 1.0 / 10000 = 1.00
    assert et.slippage == pytest.approx(1.00)


# ---- input validation ----------------------------------------------------


def test_zero_median_daily_volume_raises() -> None:
    with pytest.raises(ValueError, match="median_daily_volume must be positive"):
        HKCostModel().execute(_buy(), 400.0, 0.0, _TEST_DATE)


def test_negative_median_daily_volume_raises() -> None:
    with pytest.raises(ValueError, match="median_daily_volume must be positive"):
        HKCostModel().execute(_buy(), 400.0, -1.0, _TEST_DATE)


# ---- cash impact ---------------------------------------------------------


def test_buy_net_cash_change_is_negative_and_includes_costs() -> None:
    et = HKCostModel().execute(_buy(), 400.0, _LIQUID_MDV, _TEST_DATE)
    # Buy: cash leaves for both the notional and the fees.
    assert et.net_cash_change == pytest.approx(-40_000 - et.total_cost)
    assert et.net_cash_change < -40_000


def test_sell_net_cash_change_is_positive_after_costs() -> None:
    et = HKCostModel().execute(_sell(), 400.0, _LIQUID_MDV, _TEST_DATE)
    # Sell: cash arrives, minus fees.
    assert et.net_cash_change == pytest.approx(40_000 - et.total_cost)
    assert 0 < et.net_cash_change < 40_000


# ---- bookkeeping --------------------------------------------------------


def test_total_cost_is_sum_of_components() -> None:
    et = HKCostModel().execute(_sell(), 400.0, 1_000_000, _TEST_DATE)
    expected = (
        et.commission + et.stamp_duty + et.sfc_levy + et.hkex_fee + et.ccass_fee + et.slippage
    )
    assert et.total_cost == pytest.approx(expected)


def test_executed_trade_carries_input_metadata() -> None:
    fill_date = dt.date(2024, 6, 15)
    et = HKCostModel().execute(
        Trade(ticker="0700.HK", shares=100.0, reference_price=400.0),
        fill_price=405.0,
        median_daily_volume=1_000_000,
        executed_at=fill_date,
    )
    assert et.ticker == "0700.HK"
    assert et.shares == 100.0
    assert et.fill_price == 405.0
    assert et.gross_notional == pytest.approx(40_500.0)
    assert et.executed_at == fill_date


def test_zero_share_trade_produces_zero_cost() -> None:
    """Edge case: a no-op trade should produce a no-op cost."""
    cm = HKCostModel()
    trade = Trade(ticker="0700.HK", shares=0.0, reference_price=400.0)
    et = cm.execute(trade, 400.0, 1_000_000, _TEST_DATE)
    assert et.gross_notional == 0.0
    assert et.total_cost == 0.0
    assert et.slippage == 0.0
    assert et.net_cash_change == 0.0


# ---- parameter overrides ------------------------------------------------


def test_overriding_bps_changes_costs() -> None:
    """Confirm params actually drive the math, not hardcoded constants."""
    default_cm = HKCostModel()
    cheap_cm = HKCostModel(commission_bps=0.5, stamp_duty_bps=5.0)

    default_et = default_cm.execute(_sell(), 400.0, _LIQUID_MDV, _TEST_DATE)
    cheap_et = cheap_cm.execute(_sell(), 400.0, _LIQUID_MDV, _TEST_DATE)

    assert cheap_et.commission < default_et.commission
    assert cheap_et.stamp_duty < default_et.stamp_duty
    assert cheap_et.total_cost < default_et.total_cost


def test_overriding_slippage_params_changes_slippage_only() -> None:
    """Slippage params shouldn't perturb the bps fees."""
    default_cm = HKCostModel()
    aggressive_cm = HKCostModel(slippage_alpha=50.0)
    trade = _buy()

    default_et = default_cm.execute(trade, 400.0, 1_000_000, _TEST_DATE)
    aggressive_et = aggressive_cm.execute(trade, 400.0, 1_000_000, _TEST_DATE)

    # Fees identical, slippage 5× higher.
    assert aggressive_et.commission == default_et.commission
    assert aggressive_et.slippage == pytest.approx(5.0 * default_et.slippage)


def test_cost_model_is_frozen() -> None:
    """Dataclass(frozen=True) — config can't change after construction."""
    cm = HKCostModel()
    with pytest.raises(AttributeError):
        cm.commission_bps = 5.0  # type: ignore[misc]  -- intentional frozen-violation
