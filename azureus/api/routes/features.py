"""Feature catalog API routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from azureus.api.schemas import FeatureSummary
from azureus.api.services import catalog

router = APIRouter(prefix="/api/v1/features", tags=["features"])


@router.get("", response_model=list[FeatureSummary])
async def list_features() -> list[FeatureSummary]:
    """List registered feature metadata."""
    return catalog.list_feature_summaries()


@router.get("/{feature_name}", response_model=FeatureSummary)
async def get_feature(feature_name: str) -> FeatureSummary:
    """Return one registered feature."""
    try:
        return catalog.get_feature_summary(feature_name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
