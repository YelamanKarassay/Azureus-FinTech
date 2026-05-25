"""Strategy catalog API routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from azureus.api.schemas import StrategyDetail, StrategySummary
from azureus.api.services import catalog

router = APIRouter(prefix="/api/v1/strategies", tags=["strategies"])


@router.get("", response_model=list[StrategySummary])
async def list_strategies() -> list[StrategySummary]:
    """List registered strategy metadata."""
    return catalog.list_strategy_summaries()


@router.get("/{strategy_id}", response_model=StrategyDetail)
async def get_strategy(strategy_id: str) -> StrategyDetail:
    """Return one registered strategy."""
    try:
        return catalog.get_strategy_detail(strategy_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{strategy_id}/params-schema", response_model=dict[str, object])
async def get_strategy_params_schema(strategy_id: str) -> dict[str, object]:
    """Return the JSON Schema for a strategy's params."""
    try:
        return catalog.get_strategy_detail(strategy_id).params_schema
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
