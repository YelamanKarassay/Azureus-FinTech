"""Central feature registry for discovery and strategy lookup."""

from __future__ import annotations

from azureus.features.base import Feature

_FEATURES: dict[str, Feature] = {}


def register(feature: Feature) -> Feature:
    """Register a feature instance by stable feature name."""
    if feature.name in _FEATURES:
        raise ValueError(f"feature already registered: {feature.name}")
    _FEATURES[feature.name] = feature
    return feature


def get_feature(name: str) -> Feature:
    """Look up one feature by name."""
    try:
        return _FEATURES[name]
    except KeyError as exc:
        raise KeyError(f"unknown feature: {name}") from exc


def list_features() -> list[Feature]:
    """Registered features sorted by name for deterministic API output."""
    return [_FEATURES[name] for name in sorted(_FEATURES)]
