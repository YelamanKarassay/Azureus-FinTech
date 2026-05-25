"""Backtest job/result query helpers."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from azureus.data.models import BacktestResult, Job
from azureus.data.models import Strategy as StrategyRecord


async def ensure_strategy_record(
    session: AsyncSession,
    *,
    strategy_id: str,
    name: str,
    description: str,
) -> None:
    """Ensure the strategy metadata FK target exists for job rows."""
    existing = await session.get(StrategyRecord, strategy_id)
    if existing is None:
        session.add(
            StrategyRecord(
                id=strategy_id,
                name=name,
                description=description,
                version="1",
                is_active=True,
            )
        )
        await session.flush()
        return
    existing.name = name
    existing.description = description
    existing.is_active = True
    await session.flush()


async def insert_job(session: AsyncSession, job: Job) -> Job:
    """Insert a job and refresh server-generated fields."""
    session.add(job)
    await session.flush()
    await session.refresh(job)
    return job


async def get_job(session: AsyncSession, job_id: UUID) -> Job | None:
    """Fetch one job by id."""
    return await session.get(Job, job_id)


async def list_recent_jobs(session: AsyncSession, limit: int) -> list[Job]:
    """Recent backtest jobs, newest first."""
    result = await session.execute(
        select(Job).where(Job.job_type == "backtest").order_by(Job.created_at.desc()).limit(limit)
    )
    return list(result.scalars())


async def get_result(session: AsyncSession, job_id: UUID) -> BacktestResult | None:
    """Fetch persisted result for one job."""
    return await session.get(BacktestResult, job_id)
