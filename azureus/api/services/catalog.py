"""Registry-backed catalog services for strategies and features."""

from __future__ import annotations

from azureus.api.schemas import FeatureSummary, StrategyDetail, StrategySummary
from azureus.features.registry import get_feature, list_features
from azureus.strategies.registry import get_strategy, list_strategies


def list_strategy_summaries() -> list[StrategySummary]:
    """Return registered strategy summaries."""
    return [
        StrategySummary(
            id=strategy_cls.id,
            name=strategy_cls.name,
            description=strategy_cls.description,
        )
        for strategy_cls in list_strategies()
    ]


def get_strategy_detail(strategy_id: str) -> StrategyDetail:
    """Return one registered strategy with its JSON params schema."""
    strategy_cls = get_strategy(strategy_id)
    return StrategyDetail(
        id=strategy_cls.id,
        name=strategy_cls.name,
        description=strategy_cls.description,
        params_schema=strategy_cls.params_model.model_json_schema(),
    )


def list_feature_summaries() -> list[FeatureSummary]:
    """Return registered feature summaries."""
    return [_feature_summary(feature_name=feature.name) for feature in list_features()]


def get_feature_summary(feature_name: str) -> FeatureSummary:
    """Return one feature summary."""
    return _feature_summary(feature_name=feature_name)


def _feature_summary(feature_name: str) -> FeatureSummary:
    feature = get_feature(feature_name)
    return FeatureSummary(
        name=feature.name,
        description=feature.description,
        family=feature.family,
        requires_metrics=list(feature.requires_metrics),
        requires_lookback_days=feature.requires_lookback_days,
    )
