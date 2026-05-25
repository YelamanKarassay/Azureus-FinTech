"""Portfolio — stateful container for cash, holdings, and snapshot history.

The backtester drives this object across simulation time. Lifecycle per
simulation day:

1. `apply_executed_trade(t)` for each filled trade returned by the cost model.
2. `mark_to_market(prices)` once at end of day with that day's closes.
3. `record_snapshot(as_of_date)` to push a frozen state copy onto the history
   list. The snapshot is what the equity curve and analytics consume.

Long-only enforcement happens here, not in the engine: any trade that
would result in negative shares for a ticker raises `LongOnlyError`.
v1 is long-only per ARCHITECTURE Appendix B; engines / strategies that
emit short trades are bugs.

HKD-only; multi-currency is out of v1. The `cash` attribute and all
monetary values are HKD floats; NUMERIC precision discipline (CLAUDE.md
"Common Mistakes" #7) applies at the DB boundary, not in-memory.
"""

from __future__ import annotations

import datetime as dt
import logging
from collections.abc import Mapping

from azureus.backtesting.value_objects import (
    ExecutedTrade,
    PortfolioSnapshot,
    Position,
)

logger = logging.getLogger(__name__)


class LongOnlyError(ValueError):
    """Raised when applying a trade would push a position into negative shares.

    v1 is long-only per ARCHITECTURE Appendix B. Negative `Trade.shares`
    means closing or trimming an existing long position — never opening
    a short.
    """


class Portfolio:
    """Mutable container tracking cash, holdings, and end-of-day snapshots."""

    def __init__(self, initial_cash: float) -> None:
        if initial_cash < 0:
            raise ValueError(f"initial_cash must be non-negative; got {initial_cash}")
        self._initial_cash: float = float(initial_cash)
        self._cash: float = float(initial_cash)
        self._holdings: dict[str, Position] = {}
        self._history: list[PortfolioSnapshot] = []

    # ---- read-only views ------------------------------------------------

    @property
    def cash(self) -> float:
        return self._cash

    @property
    def initial_cash(self) -> float:
        return self._initial_cash

    @property
    def holdings(self) -> Mapping[str, Position]:
        """Read-only view of current holdings."""
        return self._holdings

    @property
    def history(self) -> tuple[PortfolioSnapshot, ...]:
        """Frozen tuple of all recorded snapshots."""
        return tuple(self._history)

    # ---- mutators (engine-driven) --------------------------------------

    def apply_executed_trade(self, trade: ExecutedTrade) -> None:
        """Apply a filled trade. Updates cash + the affected position.

        Raises `LongOnlyError` if the resulting share count would be
        negative. The trade's `net_cash_change` is the signed cash impact
        (negative for buys, positive for sells net of fees) and the cost
        model has already accounted for all fee/slippage components.
        """
        current = self._holdings.get(trade.ticker)
        current_shares = current.shares if current is not None else 0.0
        new_shares = current_shares + trade.shares

        if new_shares < 0:
            raise LongOnlyError(
                f"long-only violation on {trade.ticker}: "
                f"current shares={current_shares}, trade={trade.shares}, "
                f"would result in {new_shares}"
            )

        self._cash += trade.net_cash_change

        if new_shares == 0:
            self._holdings.pop(trade.ticker, None)
        else:
            self._holdings[trade.ticker] = Position(
                ticker=trade.ticker,
                shares=new_shares,
                last_price=trade.fill_price,
                market_value=new_shares * trade.fill_price,
            )

    def mark_to_market(self, prices: Mapping[str, float]) -> None:
        """Refresh every held position's `last_price` and `market_value`.

        Raises `KeyError` if any currently-held ticker is missing from
        `prices`. The engine is responsible for assembling a complete
        price dict for the day; a missing ticker would silently corrupt
        downstream metrics if we let it slide.
        """
        new_holdings: dict[str, Position] = {}
        for ticker, pos in self._holdings.items():
            if ticker not in prices:
                raise KeyError(f"mark_to_market: missing price for held ticker {ticker!r}")
            price = prices[ticker]
            new_holdings[ticker] = Position(
                ticker=ticker,
                shares=pos.shares,
                last_price=price,
                market_value=pos.shares * price,
            )
        self._holdings = new_holdings

    def record_snapshot(self, as_of_date: dt.date) -> PortfolioSnapshot:
        """Push a frozen snapshot of current state onto history; return it.

        The snapshot's `holdings` dict is a *copy* — later mutations to
        `self._holdings` cannot affect previously-recorded snapshots.
        `Position` values are frozen so their internals also can't change.
        """
        snapshot = PortfolioSnapshot(
            as_of_date=as_of_date,
            cash=self._cash,
            total_value=self.total_value(),
            holdings=dict(self._holdings),
        )
        self._history.append(snapshot)
        return snapshot

    # ---- derived state --------------------------------------------------

    def total_value(self) -> float:
        """Cash + sum of position market values, in HKD."""
        return self._cash + sum(p.market_value for p in self._holdings.values())

    def weights(self) -> dict[str, float]:
        """Per-ticker weight as fraction of total value.

        Cash is implicit — `sum(weights().values())` is the invested
        fraction; cash weight is `1 - sum`. Returns empty dict if the
        portfolio has no positive total value (e.g., zero initial cash
        and no holdings).
        """
        total = self.total_value()
        if total <= 0:
            return {}
        return {ticker: pos.market_value / total for ticker, pos in self._holdings.items()}
