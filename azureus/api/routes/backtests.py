"""Backtest job API routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from azureus.api.schemas import (
    BacktestCreateRequest,
    BacktestCreateResponse,
    BacktestResultResponse,
    BacktestSeriesResponse,
    BacktestStatusResponse,
)
from azureus.api.services import backtests

router = APIRouter(prefix="/api/v1/backtests", tags=["backtests"])


@router.post(
    "",
    response_model=BacktestCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_backtest(request: BacktestCreateRequest) -> BacktestCreateResponse:
    """Create and enqueue an asynchronous backtest job."""
    try:
        return await backtests.create_backtest_job(request)
    except backtests.UnknownStrategyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except backtests.InvalidStrategyParamsError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except backtests.BacktestQueueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("", response_model=list[BacktestStatusResponse])
async def list_backtests(
    limit: int = Query(default=20, ge=1, le=100),
) -> list[BacktestStatusResponse]:
    """List recent backtest jobs."""
    return await backtests.list_backtest_statuses(limit=limit)


@router.get("/{job_id}", response_model=BacktestStatusResponse)
async def get_backtest(job_id: UUID) -> BacktestStatusResponse:
    """Return one backtest job status."""
    try:
        return await backtests.get_backtest_status(job_id)
    except backtests.BacktestNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{job_id}/result", response_model=BacktestResultResponse)
async def get_backtest_result(job_id: UUID) -> BacktestResultResponse:
    """Return full persisted backtest result."""
    try:
        return await backtests.get_backtest_result(job_id)
    except backtests.BacktestNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except backtests.BacktestResultNotReadyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/{job_id}/equity-curve", response_model=BacktestSeriesResponse)
async def get_equity_curve(job_id: UUID) -> BacktestSeriesResponse:
    """Return only the equity curve rows for a persisted result."""
    return await _get_series(job_id, "equity_curve")


@router.get("/{job_id}/holdings", response_model=BacktestSeriesResponse)
async def get_holdings(job_id: UUID) -> BacktestSeriesResponse:
    """Return only holdings rows for a persisted result."""
    return await _get_series(job_id, "holdings")


@router.get("/{job_id}/trades", response_model=BacktestSeriesResponse)
async def get_trades(job_id: UUID) -> BacktestSeriesResponse:
    """Return only trade rows for a persisted result."""
    return await _get_series(job_id, "trades")


async def _get_series(job_id: UUID, series_name: str) -> BacktestSeriesResponse:
    try:
        return await backtests.get_result_series(job_id, series_name)
    except backtests.BacktestNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except backtests.BacktestResultNotReadyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
