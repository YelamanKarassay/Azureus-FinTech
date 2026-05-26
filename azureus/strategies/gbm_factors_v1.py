"""Strategy 2: LightGBM on Strategy 1 factor features."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any, ClassVar, Literal, cast

import numpy as np
import pandas as pd
from pydantic import Field

from azureus.features.base import Feature
from azureus.features.registry import get_feature
from azureus.features.scoring import feature_matrix, sector_rank_zscore
from azureus.models.cv.purged_kfold import PurgedKFold
from azureus.models.cv.walk_forward import WalkForwardWindow, expanding_windows
from azureus.models.gbm import (
    feature_importance,
    select_hyperparams_by_ic,
    spearman_ic,
    train_lightgbm_regressor,
)
from azureus.models.mlflow_tracking import log_gbm_window_run
from azureus.strategies.base import Strategy, StrategyContext, StrategyParams
from azureus.strategies.multi_factor_v1 import (
    _DEFAULT_FEATURE_NAMES,
    _LIQUIDITY_LOOKBACK_DAYS,
    _MIN_LIQUIDITY_OBSERVATIONS,
    _MONTHS_BY_FREQUENCY,
    _select_long_tickers,
)
from azureus.utils.dates import previous_trading_day, roll_to_trading_day, trading_days_between


class GBMFactorsV1Params(StrategyParams):
    """Parameters for Strategy 2."""

    universe_id: str = Field(default="HSI", min_length=1)
    training_warmup_years: int = Field(default=4, ge=1, le=10)
    oos_window_months: int = Field(default=6, ge=1, le=24)
    cv_folds: int = Field(default=5, ge=2, le=10)
    embargo_days: int = Field(default=5, ge=0, le=30)
    label_horizon_days: int = Field(default=21, ge=5, le=63)
    n_long: int = Field(default=20, ge=10, le=40)
    rebalance_frequency: Literal["monthly", "quarterly"] = "monthly"
    sector_neutral: bool = True
    model_cache: bool = True
    liquidity_threshold_usd: float = Field(default=1_000_000.0, ge=0.0)
    random_seed: int = Field(default=42, ge=0)
    sector_map: dict[str, str] = Field(default_factory=dict)


@dataclass(frozen=True)
class _TrainedWindow:
    window: WalkForwardWindow
    model: Any
    feature_names: list[str]
    params: dict[str, Any]
    metrics: dict[str, float]


class GBMFactorsV1Strategy(Strategy):
    """Long-only Strategy 2: non-linear GBM over PIT factor features."""

    id: ClassVar[str] = "gbm_factors_v1"
    name: ClassVar[str] = "GBM Factors Strategy v1"
    description: ClassVar[str] = (
        "LightGBM strategy using Strategy 1 factor features with purged CV "
        "and walk-forward training."
    )
    params_model: ClassVar[type[GBMFactorsV1Params]] = GBMFactorsV1Params

    def _setup(self) -> None:
        self._features: list[Feature] = [get_feature(name) for name in _DEFAULT_FEATURE_NAMES]
        self._trained_windows: list[_TrainedWindow] = []
        self.mlflow_run_ids: dict[str, str] = {}
        self.diagnostics: dict[str, Any] = {}

    @property
    def gbm_params(self) -> GBMFactorsV1Params:
        """Typed view of validated params."""
        return cast(GBMFactorsV1Params, self.params)

    def fit(self, train_start: dt.date, train_end: dt.date) -> None:
        """Train expanding-window LightGBM models before the backtest runs."""
        params = self.gbm_params
        windows = expanding_windows(
            start=train_start,
            end=train_end,
            warmup_years=params.training_warmup_years,
            oos_window_months=params.oos_window_months,
        )
        sample_dates = [
            previous_trading_day(date) for date in self.rebalance_dates(train_start, train_end)
        ]
        dataset = build_strategy2_dataset(
            strategy=self,
            sample_dates=sample_dates,
            label_horizon_days=params.label_horizon_days,
        )
        if dataset.empty:
            self.diagnostics = _empty_diagnostics("no complete Strategy 2 training samples")
            return

        ic_rows: list[dict[str, Any]] = []
        importances: dict[str, float] = {}
        for window in windows:
            train = dataset[
                (dataset["sample_date"] >= window.train_start)
                & (dataset["sample_date"] <= window.train_end)
            ]
            if len(train) < max(30, params.cv_folds * 5):
                continue
            features = train[self._feature_names()].astype(float)
            labels = train["label"].astype(float)
            splitter = PurgedKFold(n_splits=params.cv_folds, embargo_days=params.embargo_days)
            best_params, cv_metrics = select_hyperparams_by_ic(
                features,
                labels,
                list(train["sample_date"]),
                list(train["label_end_date"]),
                splitter,
                seed=params.random_seed,
            )
            model = train_lightgbm_regressor(features, labels, best_params, seed=params.random_seed)
            trained = _TrainedWindow(
                window=window,
                model=model,
                feature_names=list(features.columns),
                params=best_params,
                metrics=cv_metrics,
            )
            self._trained_windows.append(trained)
            importances = _merge_importance(
                importances,
                feature_importance(model, trained.feature_names),
            )
            ic_rows.extend(_oos_ic_rows(trained, dataset))
            run_id = log_gbm_window_run(
                strategy_id=self.id,
                window_id=window.window_id,
                model=model,
                params={**best_params, **params.model_dump(mode="json")},
                metrics=cv_metrics,
                tags={
                    "data_provider": self.data.provider_name,
                    "oos_start": window.oos_start.isoformat(),
                    "oos_end": window.oos_end.isoformat(),
                },
            )
            if run_id:
                self.mlflow_run_ids[window.window_id] = run_id

        self.diagnostics = _diagnostics(ic_rows, importances, self.mlflow_run_ids)

    def rebalance_dates(self, start: dt.date, end: dt.date) -> list[dt.date]:
        """First HKEX trading day of each configured calendar month."""
        months = _MONTHS_BY_FREQUENCY[self.gbm_params.rebalance_frequency]
        dates: list[dt.date] = []
        for year in range(start.year, end.year + 1):
            for month in months:
                rolled = roll_to_trading_day(dt.date(year, month, 1))
                if start <= rolled <= end:
                    dates.append(rolled)
        return dates

    def target_weights(self, ctx: StrategyContext) -> dict[str, float]:
        """Predict next-period returns and select the highest-ranked names."""
        trained = self._model_for(ctx.as_of_date)
        if trained is None:
            return {}
        frame = self._feature_frame(ctx.universe, ctx.as_of_date)
        if frame.empty:
            return {}
        features = frame.reindex(columns=trained.feature_names).dropna(how="any")
        if features.empty:
            return {}
        predictions = pd.Series(
            trained.model.predict(features),
            index=features.index.astype(str),
            dtype="float64",
            name="prediction",
        )
        sectors = (
            self._sectors_for(list(predictions.index)) if self.gbm_params.sector_neutral else None
        )
        selected = _select_long_tickers(
            scores=predictions,
            n_long=self.gbm_params.n_long,
            sectors=sectors,
            sector_neutral=self.gbm_params.sector_neutral,
        )
        if not selected:
            return {}
        weight = 1.0 / len(selected)
        return dict.fromkeys(selected, weight)

    def _feature_frame(self, tickers: list[str], as_of_date: dt.date) -> pd.DataFrame:
        liquid = self._liquid_tickers(list(dict.fromkeys(tickers)), as_of_date)
        if not liquid:
            return pd.DataFrame()
        values = {
            feature.name: feature.compute(self.data, liquid, as_of_date)
            for feature in self._features
        }
        raw = feature_matrix(values, tickers=liquid).dropna(how="any")
        if raw.empty:
            return raw
        sectors = self._sectors_for(list(raw.index)) if self.gbm_params.sector_neutral else None
        scored = {
            column: sector_rank_zscore(raw[column], sectors=sectors) for column in raw.columns
        }
        return feature_matrix(scored, tickers=list(raw.index)).dropna(how="any")

    def _feature_names(self) -> list[str]:
        return [feature.name for feature in self._features]

    def _model_for(self, as_of_date: dt.date) -> _TrainedWindow | None:
        for trained in self._trained_windows:
            if trained.window.oos_start <= as_of_date <= trained.window.oos_end:
                return trained
        return None

    def _liquid_tickers(self, tickers: list[str], as_of_date: dt.date) -> list[str]:
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
        frame["turnover"] = frame["price"] * frame["volume"]
        counts = frame.groupby("ticker")["turnover"].count()
        medians = frame.groupby("ticker")["turnover"].median()
        liquid = {
            str(ticker)
            for ticker in medians.index
            if counts.get(ticker, 0) >= _MIN_LIQUIDITY_OBSERVATIONS
            and float(medians.loc[ticker]) >= self.gbm_params.liquidity_threshold_usd
        }
        return [ticker for ticker in tickers if ticker in liquid]

    def _sectors_for(self, tickers: list[str]) -> dict[str, str]:
        sector_map = self.gbm_params.sector_map
        return {ticker: sector_map.get(ticker) or "Unknown" for ticker in tickers}


def build_strategy2_dataset(
    *,
    strategy: GBMFactorsV1Strategy,
    sample_dates: list[dt.date],
    label_horizon_days: int,
) -> pd.DataFrame:
    """Build Strategy 2 ticker-date feature rows with forward labels."""
    rows: list[pd.DataFrame] = []
    params = strategy.gbm_params
    for sample_date in sorted(set(sample_dates)):
        universe = strategy.data.get_universe(params.universe_id, sample_date)
        features = strategy._feature_frame(universe, sample_date)
        if features.empty:
            continue
        labels = _forward_sector_neutral_labels(
            strategy=strategy,
            tickers=list(features.index.astype(str)),
            as_of_date=sample_date,
            horizon_days=label_horizon_days,
        )
        if labels.empty:
            continue
        frame = features.join(labels[["label", "label_end_date"]], how="inner")
        if frame.empty:
            continue
        frame["sample_date"] = sample_date
        frame["ticker"] = frame.index.astype(str)
        rows.append(frame.reset_index(drop=True))
    if not rows:
        return pd.DataFrame()
    return pd.concat(rows, ignore_index=True).dropna(how="any")


def _forward_sector_neutral_labels(
    *,
    strategy: GBMFactorsV1Strategy,
    tickers: list[str],
    as_of_date: dt.date,
    horizon_days: int,
) -> pd.DataFrame:
    trading_days = trading_days_between(
        as_of_date,
        as_of_date + dt.timedelta(days=horizon_days * 3),
    )
    if len(trading_days) <= horizon_days:
        return pd.DataFrame()
    label_end = trading_days[horizon_days]
    prices = strategy.data.get_prices(
        tickers=tickers,
        start=as_of_date,
        end=label_end,
        fields=("adjusted_close", "close"),
    )
    if prices.empty:
        return pd.DataFrame()
    matrix = _price_matrix(prices)
    if as_of_date not in matrix.index or label_end not in matrix.index:
        return pd.DataFrame()
    raw_returns = cast(
        pd.Series,
        matrix.loc[label_end].divide(matrix.loc[as_of_date]).subtract(1.0),
    )
    returns = pd.Series(pd.to_numeric(raw_returns, errors="coerce")).dropna()
    if strategy.gbm_params.sector_neutral:
        sectors = pd.Series(strategy._sectors_for(list(returns.index)), dtype="string")
        returns = returns - returns.groupby(sectors).transform("mean")
    out = pd.DataFrame({"label": returns.astype(float), "label_end_date": label_end})
    out.index.name = "ticker"
    return out


def _price_matrix(prices: pd.DataFrame) -> pd.DataFrame:
    frame = prices.copy()
    frame["date"] = pd.to_datetime(frame["date"]).dt.date
    adjusted = pd.to_numeric(frame["adjusted_close"], errors="coerce")
    close = pd.to_numeric(frame["close"], errors="coerce")
    frame["price"] = adjusted.fillna(close)
    return frame.pivot_table(index="date", columns="ticker", values="price", aggfunc="last")


def _oos_ic_rows(trained: _TrainedWindow, dataset: pd.DataFrame) -> list[dict[str, Any]]:
    oos = dataset[
        (dataset["sample_date"] >= trained.window.oos_start)
        & (dataset["sample_date"] <= trained.window.oos_end)
    ]
    rows: list[dict[str, Any]] = []
    for sample_date, group in oos.groupby("sample_date"):
        features = group[trained.feature_names].astype(float)
        predictions = pd.Series(trained.model.predict(features), index=group.index)
        ic = spearman_ic(predictions, group["label"].astype(float))
        if np.isfinite(ic):
            rows.append(
                {
                    "date": sample_date,
                    "ic": float(ic),
                    "window_id": trained.window.window_id,
                    "n": int(len(group)),
                }
            )
    return rows


def _diagnostics(
    ic_rows: list[dict[str, Any]],
    importances: dict[str, float],
    mlflow_run_ids: dict[str, str],
) -> dict[str, Any]:
    values = [row["ic"] for row in ic_rows]
    mean_ic = float(np.mean(values)) if values else None
    ic_std = float(np.std(values, ddof=1)) if len(values) > 1 else None
    return {
        "ic_series": [
            {
                "date": (
                    row["date"].isoformat()
                    if isinstance(row["date"], dt.date)
                    else str(row["date"])
                ),
                "ic": row["ic"],
                "window_id": row["window_id"],
                "n": row["n"],
            }
            for row in ic_rows
        ],
        "mean_ic": mean_ic,
        "ic_std": ic_std,
        "ic_ir": mean_ic / ic_std if mean_ic is not None and ic_std and ic_std > 0.0 else None,
        "feature_importance": importances,
        "mlflow_run_ids": mlflow_run_ids,
    }


def _empty_diagnostics(reason: str) -> dict[str, Any]:
    return {
        "ic_series": [],
        "mean_ic": None,
        "ic_std": None,
        "ic_ir": None,
        "feature_importance": {},
        "mlflow_run_ids": {},
        "reason": reason,
    }


def _merge_importance(current: dict[str, float], new: dict[str, float]) -> dict[str, float]:
    merged = dict(current)
    for key, value in new.items():
        merged[key] = merged.get(key, 0.0) + value
    return merged
