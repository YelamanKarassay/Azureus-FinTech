"""LightGBM model helpers for Strategy 2."""

from __future__ import annotations

from collections.abc import Iterable
from itertools import product
from typing import Any

import lightgbm as lgb
import numpy as np
import pandas as pd

from azureus.models.cv.purged_kfold import PurgedKFold

GBM_FEATURE_FRACTION = 0.8
GBM_BAGGING_FRACTION = 0.8
RANDOM_SEED = 42


def strategy2_param_grid() -> list[dict[str, Any]]:
    """The locked 24-combination Strategy 2 hyperparameter grid."""
    return [
        {
            "num_leaves": num_leaves,
            "learning_rate": learning_rate,
            "n_estimators": n_estimators,
            "min_child_samples": min_child_samples,
            "feature_fraction": GBM_FEATURE_FRACTION,
            "bagging_fraction": GBM_BAGGING_FRACTION,
        }
        for num_leaves, learning_rate, n_estimators, min_child_samples in product(
            [15, 31, 63],
            [0.05, 0.1],
            [200, 500],
            [20, 50],
        )
    ]


def train_lightgbm_regressor(
    features: pd.DataFrame,
    labels: pd.Series,
    params: dict[str, Any],
    *,
    seed: int = RANDOM_SEED,
) -> lgb.LGBMRegressor:
    """Train one deterministic LightGBM regressor."""
    model = lgb.LGBMRegressor(
        objective="regression",
        random_state=seed,
        bagging_seed=seed,
        feature_fraction_seed=seed,
        verbosity=-1,
        n_jobs=1,
        **params,
    )
    model.fit(features, labels)
    return model


def select_hyperparams_by_ic(
    features: pd.DataFrame,
    labels: pd.Series,
    sample_dates: list[Any],
    label_end_dates: list[Any],
    splitter: PurgedKFold,
    grid: Iterable[dict[str, Any]] | None = None,
    *,
    seed: int = RANDOM_SEED,
) -> tuple[dict[str, Any], dict[str, float]]:
    """Choose hyperparameters by mean purged-CV Spearman IC."""
    candidates = list(grid or strategy2_param_grid())
    if not candidates:
        raise ValueError("hyperparameter grid is empty")
    best_params = candidates[0]
    best_metrics = {"mean_cv_ic": float("-inf"), "std_cv_ic": 0.0, "ic_ir": 0.0}

    for params in candidates:
        fold_ics: list[float] = []
        for train_idx, test_idx in splitter.split(sample_dates, label_end_dates):
            if len(train_idx) < 10 or len(test_idx) < 3:
                continue
            train_positions = np.asarray(train_idx, dtype=int)
            test_positions = np.asarray(test_idx, dtype=int)
            model = train_lightgbm_regressor(
                features.iloc[train_positions],
                labels.iloc[train_positions],
                params,
                seed=seed,
            )
            predictions = pd.Series(
                model.predict(features.iloc[test_positions]),
                index=labels.iloc[test_positions].index,
            )
            ic = spearman_ic(predictions, labels.iloc[test_positions])
            if np.isfinite(ic):
                fold_ics.append(ic)
        metrics = _ic_metrics(fold_ics)
        if metrics["mean_cv_ic"] > best_metrics["mean_cv_ic"]:
            best_params = params
            best_metrics = metrics

    if best_metrics["mean_cv_ic"] == float("-inf"):
        best_metrics = {"mean_cv_ic": 0.0, "std_cv_ic": 0.0, "ic_ir": 0.0}
    return best_params, best_metrics


def spearman_ic(predictions: pd.Series, labels: pd.Series) -> float:
    """Spearman rank information coefficient."""
    aligned = pd.concat(
        [pd.to_numeric(predictions, errors="coerce"), pd.to_numeric(labels, errors="coerce")],
        axis=1,
    ).dropna()
    if len(aligned) < 3:
        return float("nan")
    corr = aligned.iloc[:, 0].rank(method="average").corr(
        aligned.iloc[:, 1].rank(method="average")
    )
    return float(corr) if pd.notna(corr) else float("nan")


def feature_importance(model: lgb.LGBMRegressor, feature_names: list[str]) -> dict[str, float]:
    """Return split-based feature importances keyed by feature name."""
    values = model.feature_importances_
    return {name: float(value) for name, value in zip(feature_names, values, strict=True)}


def _ic_metrics(values: list[float]) -> dict[str, float]:
    finite = [value for value in values if np.isfinite(value)]
    if not finite:
        return {"mean_cv_ic": float("-inf"), "std_cv_ic": 0.0, "ic_ir": 0.0}
    mean = float(np.mean(finite))
    std = float(np.std(finite, ddof=1)) if len(finite) > 1 else 0.0
    return {
        "mean_cv_ic": mean,
        "std_cv_ic": std,
        "ic_ir": mean / std if std > 0.0 else 0.0,
    }
