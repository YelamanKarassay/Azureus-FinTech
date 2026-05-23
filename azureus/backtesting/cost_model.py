"""`HKCostModel` — Hong Kong transaction cost model per ARCHITECTURE §4.8.

The cost model is the only place that knows about HK fee structure:

| Component                     | Buy side  | Sell side |
|-------------------------------|-----------|-----------|
| Commission (institutional)    |  2.0 bps  |  2.0 bps  |
| Stamp duty                    |    —      | 10.0 bps  |
| SFC transaction levy          |  0.27 bps |  0.27 bps |
| HKEX trading fee              |  0.5 bps  |  0.5 bps  |
| CCASS settlement              |  0.2 bps  |  0.2 bps  |
| **Per-side total (no slip.)** | **2.97**  | **12.97** |
| **Round-trip**                |           | **15.94** |

Plus volume-aware slippage on top of the bps fees:

    slippage_bps = α × (trade_notional / median_daily_volume) ** β

Defaults α = 10, β = 0.5 (square-root impact). Bps are interpreted in
the standard way: bps × notional / 10000 = dollars.

**Interview narrative** (per §4.8): many backtests assume ~5 bps
round-trip. Ours assumes ~16 bps + volume-scaled slippage. Reported
Sharpe ratios are correspondingly lower but more credible.

The model is a frozen dataclass — instances are configuration, the
`execute()` method does all the work. All bps and slippage parameters
override-able at construction so backtests can sensitivity-test cost
assumptions.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from azureus.backtesting.value_objects import ExecutedTrade, Trade

_BPS_PER_UNIT = 10_000.0


@dataclass(frozen=True)
class HKCostModel:
    """HK-specific transaction cost model. See module docstring for fee table."""

    commission_bps: float = 2.0
    stamp_duty_bps: float = 10.0  # sell only — asymmetric
    sfc_levy_bps: float = 0.27
    hkex_fee_bps: float = 0.5
    ccass_fee_bps: float = 0.2
    slippage_alpha: float = 10.0
    slippage_beta: float = 0.5

    def execute(
        self,
        trade: Trade,
        fill_price: float,
        median_daily_volume: float,
        executed_at: dt.date,
    ) -> ExecutedTrade:
        """Fill `trade` at `fill_price`, computing all cost components.

        Args:
            trade: The intended trade. `trade.shares` is signed
                (positive = buy, negative = sell).
            fill_price: Per-share fill price in HKD (typically today's close).
            median_daily_volume: Rolling median daily volume **in shares**,
                used to scale slippage. Must be > 0 — illiquid names should
                be excluded upstream by the strategy's liquidity filter.
            executed_at: Trading date on which the fill occurred.

        Returns:
            `ExecutedTrade` with every cost component broken out for
            analytics + portfolio bookkeeping.

        Raises:
            ValueError: if `median_daily_volume <= 0`. We fail loud rather
                than silently degrading slippage on illiquid names.
        """
        if median_daily_volume <= 0:
            raise ValueError(
                f"median_daily_volume must be positive; got {median_daily_volume} "
                f"for {trade.ticker} on {executed_at}"
            )

        is_sell = trade.shares < 0
        abs_shares = abs(trade.shares)
        gross_notional = abs_shares * fill_price

        commission = gross_notional * self.commission_bps / _BPS_PER_UNIT
        stamp_duty = gross_notional * self.stamp_duty_bps / _BPS_PER_UNIT if is_sell else 0.0
        sfc_levy = gross_notional * self.sfc_levy_bps / _BPS_PER_UNIT
        hkex_fee = gross_notional * self.hkex_fee_bps / _BPS_PER_UNIT
        ccass_fee = gross_notional * self.ccass_fee_bps / _BPS_PER_UNIT

        # Volume-aware slippage: alpha * (notional/MDV)^beta is the slippage
        # in bps; convert to dollars the same way the other fees do.
        if gross_notional > 0:
            slippage_bps = (
                self.slippage_alpha * (gross_notional / median_daily_volume) ** self.slippage_beta
            )
            slippage = gross_notional * slippage_bps / _BPS_PER_UNIT
        else:
            slippage = 0.0

        total_cost = commission + stamp_duty + sfc_levy + hkex_fee + ccass_fee + slippage

        # Cash impact is signed: buying decreases cash, selling increases it.
        # `-shares * fill_price` handles the sign automatically (buy=positive
        # shares, so -shares*price is negative); then subtract total_cost
        # (which always reduces cash, regardless of direction).
        net_cash_change = -trade.shares * fill_price - total_cost

        return ExecutedTrade(
            ticker=trade.ticker,
            executed_at=executed_at,
            shares=trade.shares,
            fill_price=fill_price,
            gross_notional=gross_notional,
            commission=commission,
            stamp_duty=stamp_duty,
            sfc_levy=sfc_levy,
            hkex_fee=hkex_fee,
            ccass_fee=ccass_fee,
            slippage=slippage,
            total_cost=total_cost,
            net_cash_change=net_cash_change,
        )
