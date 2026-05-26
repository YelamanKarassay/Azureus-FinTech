"""RQ task definitions for asynchronous backtest execution."""

from __future__ import annotations

import datetime as dt
import logging
from uuid import UUID

from azureus.backtesting.cost_model import HKCostModel
from azureus.backtesting.engine import BacktestConfig, BacktestEngine
from azureus.backtesting.results import BacktestResult as EngineBacktestResult
from azureus.data.db import sync_session
from azureus.data.models import BacktestResult as BacktestResultRecord
from azureus.data.models import Job
from azureus.data.sources.auditing import AuditingDataSource
from azureus.data.sources.factory import get_data_source
from azureus.strategies.registry import get_strategy

logger = logging.getLogger(__name__)


def run_backtest_job(job_id: str) -> None:
    """Run one queued backtest job and persist its result."""
    parsed_job_id = UUID(job_id)
    try:
        job = _mark_running(parsed_job_id)
        result = _execute_job(job)
        _mark_completed(parsed_job_id, result)
    except Exception as exc:
        logger.exception("backtest job failed: %s", job_id)
        _mark_failed(parsed_job_id, str(exc))
        raise


def _mark_running(job_id: UUID) -> Job:
    with sync_session() as session:
        job = session.get(Job, job_id)
        if job is None or job.job_type != "backtest":
            raise ValueError(f"unknown backtest job: {job_id}")
        job.status = "running"
        job.started_at = _utc_now()
        job.error_message = None
        session.flush()
        session.refresh(job)
        return job


def _execute_job(job: Job) -> tuple[EngineBacktestResult, dict[str, object] | None]:
    strategy_id = str(job.params["strategy_id"])
    strategy_cls = get_strategy(strategy_id)
    strategy_params = strategy_cls.params_model.model_validate(job.params["strategy_params"])
    data_source = get_data_source(job.data_provider)
    audited_source = AuditingDataSource(data_source)
    strategy = strategy_cls(strategy_params, audited_source)
    start = dt.date.fromisoformat(str(job.params["start"]))
    end = dt.date.fromisoformat(str(job.params["end"]))
    strategy.fit(start, end)
    config = BacktestConfig(
        start=start,
        end=end,
        initial_capital=float(job.params["initial_capital"]),
        universe_id=str(job.params["universe_id"]),
        audit=True,
    )
    engine = BacktestEngine(
        strategy=strategy,
        data_source=data_source,
        cost_model=HKCostModel(),
        config=config,
    )
    result = engine.run()
    diagnostics = getattr(strategy, "diagnostics", None)
    if isinstance(diagnostics, dict):
        result = result.model_copy(update={"diagnostics": diagnostics})
    run_ids = getattr(strategy, "mlflow_run_ids", None)
    return result, run_ids if isinstance(run_ids, dict) else None


def _mark_completed(
    job_id: UUID,
    result_and_run_ids: tuple[EngineBacktestResult, dict[str, object] | None],
) -> None:
    result, mlflow_run_ids = result_and_run_ids
    payload = result.as_dict()
    with sync_session() as session:
        job = session.get(Job, job_id)
        if job is None:
            raise ValueError(f"unknown backtest job: {job_id}")
        session.merge(
            BacktestResultRecord(
                job_id=job_id,
                summary=payload["summary"],
                equity_curve=payload["equity_curve"],
                holdings=payload["holdings"],
                trades=payload["trades"],
                diagnostics=payload["diagnostics"],
            )
        )
        job.mlflow_run_ids = mlflow_run_ids
        job.status = "completed"
        job.completed_at = _utc_now()
        job.error_message = None


def _mark_failed(job_id: UUID, message: str) -> None:
    with sync_session() as session:
        job = session.get(Job, job_id)
        if job is None:
            return
        job.status = "failed"
        job.completed_at = _utc_now()
        job.error_message = message


def _utc_now() -> dt.datetime:
    return dt.datetime.now(tz=dt.UTC)
