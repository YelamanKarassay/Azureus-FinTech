"""Cross-sectional feature scoring helpers for Strategy 1."""

from __future__ import annotations

from collections.abc import Mapping

import pandas as pd


def feature_matrix(
    feature_values: Mapping[str, pd.Series],
    tickers: list[str] | None = None,
) -> pd.DataFrame:
    """Align sparse feature series into a ticker × feature matrix."""
    if not feature_values:
        return pd.DataFrame(index=pd.Index(tickers or [], name="ticker"))

    matrix = pd.concat(
        [values.rename(name) for name, values in feature_values.items()],
        axis=1,
        join="outer",
    )
    matrix.index.name = "ticker"
    if tickers is not None:
        matrix = matrix.reindex(tickers)
    return matrix.astype(float)


def feature_availability_filter(
    feature_values: Mapping[str, pd.Series],
    tickers: list[str] | None = None,
) -> list[str]:
    """Return tickers with every requested feature present.

    This is the v1 no-imputation rule in code: incomplete rows are excluded
    before ranking or portfolio construction.
    """
    matrix = feature_matrix(feature_values, tickers=tickers)
    if matrix.empty:
        return []
    return matrix.dropna(how="any").index.astype(str).tolist()


def sector_rank_zscore(
    values: pd.Series,
    sectors: Mapping[str, str] | pd.Series | None = None,
) -> pd.Series:
    """Rank values within sectors and z-score the resulting cross-section."""
    clean = pd.to_numeric(values, errors="coerce").dropna().astype(float)
    clean.name = values.name
    if clean.empty:
        return clean

    if sectors is None:
        ranked = clean.rank(method="average", pct=True)
    else:
        sector_series = _sector_series(sectors).reindex(clean.index)
        frame = pd.DataFrame({"value": clean, "sector": sector_series}).dropna()
        ranked = frame.groupby("sector")["value"].rank(method="average", pct=True)
        ranked.index = frame.index
        ranked = ranked.reindex(clean.index).dropna()

    scores = _zscore(ranked)
    scores.name = values.name
    return scores


def family_scores(
    feature_values: Mapping[str, pd.Series],
    feature_families: Mapping[str, str],
    sectors: Mapping[str, str] | pd.Series | None = None,
    tickers: list[str] | None = None,
) -> pd.DataFrame:
    """Compute mean rank-z-score per feature family over complete tickers."""
    complete_tickers = feature_availability_filter(feature_values, tickers=tickers)
    if not complete_tickers:
        return pd.DataFrame()

    matrix = feature_matrix(feature_values, tickers=complete_tickers)
    scored_features: dict[str, pd.Series] = {}
    for feature_name in matrix.columns:
        scored_features[feature_name] = sector_rank_zscore(matrix[feature_name], sectors=sectors)

    scored_matrix = feature_matrix(scored_features, tickers=complete_tickers)
    family_columns: dict[str, pd.Series] = {}
    for family in sorted(set(feature_families.values())):
        feature_names = [
            name
            for name, candidate_family in feature_families.items()
            if candidate_family == family and name in scored_matrix.columns
        ]
        if feature_names:
            family_columns[family] = scored_matrix[feature_names].mean(axis=1)

    return feature_matrix(family_columns, tickers=complete_tickers)


def composite_score(
    scores_by_family: pd.DataFrame,
    family_weights: Mapping[str, float],
) -> pd.Series:
    """Weighted composite score from family-score columns."""
    if scores_by_family.empty:
        return pd.Series(dtype="float64", name="composite_score")

    usable_weights = {
        family: float(weight)
        for family, weight in family_weights.items()
        if family in scores_by_family.columns and weight > 0.0
    }
    total_weight = sum(usable_weights.values())
    if total_weight <= 0.0:
        raise ValueError("family_weights must contain at least one positive usable weight")

    weighted = pd.Series(0.0, index=scores_by_family.index, dtype="float64")
    for family, weight in usable_weights.items():
        weighted = weighted.add(scores_by_family[family] * (weight / total_weight), fill_value=0.0)
    weighted.name = "composite_score"
    return weighted.dropna()


def _sector_series(sectors: Mapping[str, str] | pd.Series) -> pd.Series:
    if isinstance(sectors, pd.Series):
        return sectors.astype("string")
    return pd.Series(sectors, dtype="string")


def _zscore(values: pd.Series) -> pd.Series:
    if len(values) < 2:
        return pd.Series(0.0, index=values.index, dtype="float64")
    std = float(values.std(ddof=0))
    if std == 0.0:
        return pd.Series(0.0, index=values.index, dtype="float64")
    return ((values - float(values.mean())) / std).astype(float)
