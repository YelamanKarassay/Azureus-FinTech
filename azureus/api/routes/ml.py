"""Read-only MLflow proxy routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from azureus.api.schemas import MLRunDetail, MLRunSummary
from azureus.api.services import ml

router = APIRouter(prefix="/api/v1/ml", tags=["ml"])


@router.get("/runs", response_model=list[MLRunSummary])
async def list_runs(
    strategy_id: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
) -> list[MLRunSummary]:
    """List recent MLflow runs."""
    return ml.list_ml_runs(strategy_id=strategy_id, limit=limit)


@router.get("/runs/{mlflow_run_id}", response_model=MLRunDetail)
async def get_run(mlflow_run_id: str) -> MLRunDetail:
    """Return one MLflow run."""
    try:
        return ml.get_ml_run(mlflow_run_id)
    except ml.MLRunNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
