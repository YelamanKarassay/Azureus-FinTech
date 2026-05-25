"""Strategy 1: multi-factor cross-sectional long-only strategy."""

from __future__ import annotations

import datetime as dt
from typing import ClassVar, Literal, cast

import pandas as pd
from pydantic import Field, field_validator

from azureus.features.base import Feature
from azureus.features.registry import get_feature
from azureus.features.scoring import composite_score, family_scores
from azureus.strategies.base import Strategy, StrategyContext, StrategyParams
from azureus.utils.dates import roll_to_trading_day

_DEFAULT_FEATURE_NAMES = (
    "earnings_yield",
    "book_to_price",
    "sales_to_price",
    "fcf_to_price",
    "roe",
    "gross_profitability",
    "debt_to_equity",
    "accruals",
    "momentum_12_1",
    "realized_vol_252d",
    "beta_252d",
)
_DEFAULT_FAMILY_WEIGHTS = {
    "value": 0.25,
    "quality": 0.25,
    "momentum": 0.25,
    "low_vol": 0.25,
}
_KNOWN_FAMILIES = frozenset(_DEFAULT_FAMILY_WEIGHTS)
_MONTHS_BY_FREQUENCY = {
    "monthly": tuple(range(1, 13)),
    "quarterly": (1, 4, 7, 10),
}
_LIQUIDITY_LOOKBACK_DAYS = 45
_MIN_LIQUIDITY_OBSERVATIONS = 5


class MultiFactorV1Params(StrategyParams):
    """Parameters for Strategy 1."""

    universe_id: str = Field(default="HSI", min_length=1)
    rebalance_frequency: Literal["monthly", "quarterly"] = "monthly"
    n_long: int = Field(default=20, ge=10, le=40)
    sector_neutral: bool = True
    factor_weights: dict[str, float] = Field(default_factory=lambda: dict(_DEFAULT_FAMILY_WEIGHTS))
    weighting_scheme: Literal["equal", "score_weighted"] = "equal"
    liquidity_threshold_usd: float = Field(default=1_000_000.0, ge=0.0)
    sector_map: dict[str, str] = Field(default_factory=dict)

    @field_validator("factor_weights")
    @classmethod
    def _validate_factor_weights(cls, value: dict[str, float]) -> dict[str, float]:
        unknown = set(value) - _KNOWN_FAMILIES
        if unknown:
            raise ValueError(f"unknown factor weight families: {sorted(unknown)}")
        positive_total = sum(weight for weight in value.values() if weight > 0.0)
        if positive_total <= 0.0:
            raise ValueError("factor_weights must contain at least one positive weight")
        return value


class MultiFactorV1Strategy(Strategy):
    """Long-only Strategy 1: value, quality, momentum, and low-vol composite."""

    id: ClassVar[str] = "multi_factor_v1"
    name: ClassVar[str] = "Multi-Factor Strategy v1"
    description: ClassVar[str] = (
        "Long-only cross-sectional value, quality, momentum, and low-vol strategy."
    )
    params_model: ClassVar[type[MultiFactorV1Params]] = MultiFactorV1Params

    def _setup(self) -> None:
        self._features: list[Feature] = [get_feature(name) for name in _DEFAULT_FEATURE_NAMES]
        self._feature_families: dict[str, str] = {
            feature.name: feature.family for feature in self._features
        }

    @property
    def multi_factor_params(self) -> MultiFactorV1Params:
        """Typed view of validated params."""
        return cast(MultiFactorV1Params, self.params)

    def rebalance_dates(self, start: dt.date, end: dt.date) -> list[dt.date]:
        """First HKEX trading day of each configured calendar month."""
        months = _MONTHS_BY_FREQUENCY[self.multi_factor_params.rebalance_frequency]
        dates: list[dt.date] = []
        for year in range(start.year, end.year + 1):
            for month in months:
                rolled = roll_to_trading_day(dt.date(year, month, 1))
                if start <= rolled <= end:
                    dates.append(rolled)
        return dates

    def target_weights(self, ctx: StrategyContext) -> dict[str, float]:
        """Compute long-only target weights for the rebalance context."""
        params = self.multi_factor_params
        ordered_universe = list(dict.fromkeys(ctx.universe))
        liquid = self._liquid_tickers(ordered_universe, ctx.as_of_date)
        if not liquid:
            return {}

        feature_values = {
            feature.name: feature.compute(self.data, liquid, ctx.as_of_date)
            for feature in self._features
        }
        sectors = self._sectors_for(liquid) if params.sector_neutral else None
        family_frame = family_scores(
            feature_values=feature_values,
            feature_families=self._feature_families,
            sectors=sectors,
            tickers=liquid,
        )
        scores = composite_score(family_frame, params.factor_weights)
        selected = _select_long_tickers(
            scores=scores,
            n_long=params.n_long,
            sectors=sectors,
            sector_neutral=params.sector_neutral,
        )
        if not selected:
            return {}
        return _target_weights(
            selected=selected,
            scores=scores,
            weighting_scheme=params.weighting_scheme,
        )

    def _liquid_tickers(self, tickers: list[str], as_of_date: dt.date) -> list[str]:
        """Filter by recent median daily turnover."""
        if not tickers:
            return []
        prices = self.data.get_prices(
            tickers=tickers,
            start=as_of_date - dt.timedelta(days=_LIQUIDITY_LOOKBACK_DAYS),
            end=as_of_date,
            fields=("adjusted_close", "close", "volume"),
        )
        if prices.empty:
            return []

        frame = prices.copy()
        adjusted = pd.to_numeric(frame["adjusted_close"], errors="coerce")
        close = pd.to_numeric(frame["close"], errors="coerce")
        frame["price"] = adjusted.fillna(close)
        frame["volume"] = pd.to_numeric(frame["volume"], errors="coerce")
        frame = frame.dropna(subset=["price", "volume"])
        frame = frame[(frame["price"] > 0.0) & (frame["volume"] > 0.0)]
        if frame.empty:
            return []

        frame["turnover"] = frame["price"] * frame["volume"]
        counts = frame.groupby("ticker")["turnover"].count()
        medians = frame.groupby("ticker")["turnover"].median()
        threshold = self.multi_factor_params.liquidity_threshold_usd
        liquid = {
            str(ticker)
            for ticker in medians.index
            if counts.get(ticker, 0) >= _MIN_LIQUIDITY_OBSERVATIONS
            and float(medians.loc[ticker]) >= threshold
        }
        return [ticker for ticker in tickers if ticker in liquid]

    def _sectors_for(self, tickers: list[str]) -> dict[str, str]:
        sector_map = self.multi_factor_params.sector_map
        return {ticker: sector_map.get(ticker) or "Unknown" for ticker in tickers}


def _select_long_tickers(
    *,
    scores: pd.Series,
    n_long: int,
    sectors: dict[str, str] | None,
    sector_neutral: bool,
) -> list[str]:
    ranked = _rank_scores(scores)
    if ranked.empty:
        return []
    target_count = min(n_long, len(ranked))
    if not sector_neutral or sectors is None:
        return ranked.head(target_count).index.astype(str).tolist()

    sector_series = pd.Series(sectors, dtype="string").reindex(ranked.index).fillna("Unknown")
    quotas = _sector_quotas(sector_series, target_count)
    selected: list[str] = []
    for sector, quota in quotas.items():
        sector_ranked = ranked[sector_series == sector]
        selected.extend(sector_ranked.head(quota).index.astype(str).tolist())

    if len(selected) < target_count:
        selected_set = set(selected)
        filler = [ticker for ticker in ranked.index.astype(str) if ticker not in selected_set]
        selected.extend(filler[: target_count - len(selected)])
    return selected[:target_count]


def _sector_quotas(sectors: pd.Series, target_count: int) -> dict[str, int]:
    counts = sectors.value_counts().sort_index()
    raw = counts / counts.sum() * target_count
    quotas = raw.astype(int).clip(upper=counts)
    remainder = target_count - int(quotas.sum())

    if remainder > 0:
        fractions = (raw - quotas).sort_values(ascending=False)
        for sector in fractions.index.astype(str):
            if remainder == 0:
                break
            if quotas.loc[sector] < counts.loc[sector]:
                quotas.loc[sector] += 1
                remainder -= 1

    if int(quotas.sum()) < target_count:
        for sector in counts.index.astype(str):
            while int(quotas.sum()) < target_count and quotas.loc[sector] < counts.loc[sector]:
                quotas.loc[sector] += 1

    return {str(sector): int(quota) for sector, quota in quotas.items() if quota > 0}


def _target_weights(
    *,
    selected: list[str],
    scores: pd.Series,
    weighting_scheme: Literal["equal", "score_weighted"],
) -> dict[str, float]:
    if weighting_scheme == "equal":
        weight = 1.0 / len(selected)
        return dict.fromkeys(selected, weight)

    selected_scores = scores.reindex(selected)
    ranks = selected_scores.rank(method="first", ascending=True)
    total = float(ranks.sum())
    if total <= 0.0:
        weight = 1.0 / len(selected)
        return dict.fromkeys(selected, weight)
    return {ticker: float(ranks.loc[ticker] / total) for ticker in selected}


def _rank_scores(scores: pd.Series) -> pd.Series:
    if scores.empty:
        return scores
    frame = pd.DataFrame(
        {
            "ticker": scores.index.astype(str),
            "score": pd.to_numeric(scores, errors="coerce").to_numpy(),
        }
    ).dropna(subset=["score"])
    if frame.empty:
        return pd.Series(dtype="float64", name=scores.name)
    frame = frame.sort_values(["score", "ticker"], ascending=[False, True])
    ranked = pd.Series(frame["score"].to_numpy(), index=frame["ticker"], dtype="float64")
    ranked.name = scores.name
    return ranked
