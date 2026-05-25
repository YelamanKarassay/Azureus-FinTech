"""Backtest API service functions."""

from __future__ import annotations

import datetime as dt
from typing import Any
from uuid import UUID

from pydantic import ValidationError
from redis import Redis
from rq import Queue

from azureus.api.queries import backtests as queries
from azureus.api.schemas import (
    BacktestCreateRequest,
    BacktestCreateResponse,
    BacktestResultResponse,
    BacktestSeriesResponse,
    BacktestStatusResponse,
)
from azureus.config import get_settings
from azureus.data.db import async_session
from azureus.data.models import Job
from azureus.strategies.registry import get_strategy
from azureus.utils.reproducibility import (
    get_dependencies_lock,
    get_git_sha,
    is_git_status_clean,
)

_BACKTEST_QUEUE_NAME = "backtests"


class BacktestServiceError(Exception):
    """Base class for expected backtest service failures."""


class UnknownStrategyError(BacktestServiceError):
    """Requested strategy id is not registered."""


class InvalidStrategyParamsError(BacktestServiceError):
    """Strategy-specific params failed validation."""


class BacktestNotFoundError(BacktestServiceError):
    """Requested job or result does not exist."""


class BacktestResultNotReadyError(BacktestServiceError):
    """Requested result is not persisted yet."""


class BacktestQueueError(BacktestServiceError):
    """RQ enqueue failed after job creation."""


async def create_backtest_job(request: BacktestCreateRequest) -> BacktestCreateResponse:
    """Validate, persist, and enqueue a backtest job."""
    try:
        strategy_cls = get_strategy(request.strategy_id)
    except KeyError as exc:
        raise UnknownStrategyError(str(exc)) from exc

    try:
        strategy_params = strategy_cls.params_model.model_validate(request.params)
    except ValidationError as exc:
        raise InvalidStrategyParamsError(str(exc)) from exc

    params_payload = _job_params_payload(
        request=request,
        strategy_params=strategy_params.model_dump(mode="json"),
    )
    now = _utc_now()
    job = Job(
        strategy_id=strategy_cls.id,
        job_type="backtest",
        status="queued",
        params=params_payload,
        code_version=get_git_sha() or "unknown",
        dependencies_lock=get_dependencies_lock(),
        git_status_clean=is_git_status_clean(),
        as_of_timestamp=now,
        data_provider=request.data_provider,
        mlflow_run_ids=None,
    )

    async with async_session() as session:
        await queries.ensure_strategy_record(
            session,
            strategy_id=strategy_cls.id,
            name=strategy_cls.name,
            description=strategy_cls.description,
        )
        inserted = await queries.insert_job(session, job)
        job_id = inserted.id

    try:
        _enqueue_backtest_job(job_id)
    except Exception as exc:
        await _mark_enqueue_failed(job_id, str(exc))
        raise BacktestQueueError(f"failed to enqueue backtest job {job_id}") from exc

    return BacktestCreateResponse(job_id=job_id, status="queued")


async def get_backtest_status(job_id: UUID) -> BacktestStatusResponse:
    """Return one backtest job status."""
    async with async_session() as session:
        job = await queries.get_job(session, job_id)
    if job is None or job.job_type != "backtest":
        raise BacktestNotFoundError(f"unknown backtest job: {job_id}")
    return _status_response(job)


async def list_backtest_statuses(limit: int = 20) -> list[BacktestStatusResponse]:
    """Return recent backtest job statuses."""
    async with async_session() as session:
        jobs = await queries.list_recent_jobs(session, limit=limit)
    return [_status_response(job) for job in jobs]


async def get_backtest_result(job_id: UUID) -> BacktestResultResponse:
    """Return persisted full result for one backtest."""
    async with async_session() as session:
        job = await queries.get_job(session, job_id)
        result = await queries.get_result(session, job_id)
    if job is None or job.job_type != "backtest":
        raise BacktestNotFoundError(f"unknown backtest job: {job_id}")
    if result is None:
        raise BacktestResultNotReadyError(f"result not ready for backtest job: {job_id}")
    return BacktestResultResponse(
        job_id=job_id,
        summary=result.summary,
        equity_curve=result.equity_curve or [],
        holdings=result.holdings or [],
        trades=result.trades or [],
    )


async def get_result_series(job_id: UUID, series_name: str) -> BacktestSeriesResponse:
    """Return one result table for chart-specific endpoints."""
    result = await get_backtest_result(job_id)
    rows = getattr(result, series_name)
    return BacktestSeriesResponse(job_id=job_id, rows=rows)


def _job_params_payload(
    *,
    request: BacktestCreateRequest,
    strategy_params: dict[str, Any],
) -> dict[str, Any]:
    universe_id = str(strategy_params.get("universe_id", "HSI"))
    return {
        "strategy_id": request.strategy_id,
        "strategy_params": strategy_params,
        "start": request.start.isoformat(),
        "end": request.end.isoformat(),
        "initial_capital": request.initial_capital,
        "universe_id": universe_id,
        "random_seed": request.random_seed,
    }


def _enqueue_backtest_job(job_id: UUID) -> None:
    settings = get_settings()
    redis = Redis.from_url(settings.redis_url)
    queue = Queue(_BACKTEST_QUEUE_NAME, connection=redis)
    queue.enqueue("azureus.worker.tasks.run_backtest_job", str(job_id))


async def _mark_enqueue_failed(job_id: UUID, message: str) -> None:
    async with async_session() as session:
        job = await queries.get_job(session, job_id)
        if job is None:
            return
        job.status = "failed"
        job.completed_at = _utc_now()
        job.error_message = message


def _status_response(job: Job) -> BacktestStatusResponse:
    return BacktestStatusResponse(
        job_id=job.id,
        strategy_id=job.strategy_id,
        job_type=job.job_type,
        status=job.status,
        params=job.params,
        data_provider=job.data_provider,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        error_message=job.error_message,
    )


def _utc_now() -> dt.datetime:
    return dt.datetime.now(tz=dt.UTC)
