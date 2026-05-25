"""RQ worker task tests."""

from __future__ import annotations

import datetime as dt
from typing import ClassVar, cast
from uuid import UUID

import pandas as pd
import pytest
from pydantic import Field
from sqlalchemy import text

from azureus.data.db import sync_session
from azureus.data.models import Job
from azureus.data.models import Strategy as StrategyRecord
from azureus.data.sources.base import DataSource
from azureus.strategies.base import Strategy, StrategyContext, StrategyParams
from azureus.worker import tasks


class WorkerTestParams(StrategyParams):
    """Params for the worker task test strategy."""

    ticker: str = Field(default="0700.HK")
    rebalance_date: dt.date = Field(default=dt.date(2024, 1, 2))


class WorkerTestStrategy(Strategy):
    """Single-rebalance, single-ticker strategy for worker tests."""

    id: ClassVar[str] = "worker_test_strategy"
    name: ClassVar[str] = "Worker Test Strategy"
    description: ClassVar[str] = "Synthetic strategy used by worker tests."
    params_model: ClassVar[type[WorkerTestParams]] = WorkerTestParams

    @property
    def worker_params(self) -> WorkerTestParams:
        return cast(WorkerTestParams, self.params)

    def rebalance_dates(self, start: dt.date, end: dt.date) -> list[dt.date]:
        rebalance_date = self.worker_params.rebalance_date
        return [rebalance_date] if start <= rebalance_date <= end else []

    def target_weights(self, ctx: StrategyContext) -> dict[str, float]:
        return {self.worker_params.ticker: 1.0}


class WorkerDataSource:
    """In-memory price source for worker tests."""

    provider_name = "worker-test"

    def __init__(self, prices: pd.DataFrame, universe: list[str]) -> None:
        self._prices = prices
        self._universe = universe

    def get_universe(self, index_id: str, as_of_date: dt.date) -> list[str]:
        return list(self._universe)

    def get_universe_history(self, index_id: str, start: dt.date, end: dt.date) -> pd.DataFrame:
        return pd.DataFrame()

    def get_prices(
        self,
        tickers: list[str],
        start: dt.date,
        end: dt.date,
        fields: tuple[str, ...] = ("close",),
    ) -> pd.DataFrame:
        mask = (
            self._prices["ticker"].isin(tickers)
            & (self._prices["date"] >= pd.Timestamp(start))
            & (self._prices["date"] <= pd.Timestamp(end))
        )
        return self._prices.loc[mask, ["date", "ticker", *fields]].copy()

    def get_fundamentals(
        self,
        tickers: list[str],
        as_of_date: dt.date,
        metrics: list[str],
    ) -> pd.DataFrame:
        return pd.DataFrame()

    def get_fundamentals_history(
        self,
        tickers: list[str],
        start: dt.date,
        end: dt.date,
        metrics: list[str],
    ) -> pd.DataFrame:
        return pd.DataFrame()

    def get_macro(self, series_ids: list[str], start: dt.date, end: dt.date) -> pd.DataFrame:
        return pd.DataFrame()

    def list_available_tickers(self, index_id: str | None = None) -> list[str]:
        return list(self._universe)

    def list_available_metrics(self) -> list[str]:
        return []


def _worker_source() -> WorkerDataSource:
    rows: list[dict[str, object]] = []
    for day in pd.bdate_range(start="2023-11-01", periods=80):
        rows.append(
            {
                "date": day,
                "ticker": "0700.HK",
                "close": 400.0,
                "volume": 10_000_000,
            }
        )
    return WorkerDataSource(pd.DataFrame(rows), ["0700.HK"])


def _seed_worker_job() -> UUID:
    with sync_session() as session:
        session.add(
            StrategyRecord(
                id=WorkerTestStrategy.id,
                name=WorkerTestStrategy.name,
                description=WorkerTestStrategy.description,
                version="1",
                is_active=True,
            )
        )
        session.flush()
        job = Job(
            strategy_id=WorkerTestStrategy.id,
            job_type="backtest",
            status="queued",
            params={
                "strategy_id": WorkerTestStrategy.id,
                "strategy_params": WorkerTestParams().model_dump(mode="json"),
                "start": "2024-01-02",
                "end": "2024-01-10",
                "initial_capital": 1_000_000.0,
                "universe_id": "HSI",
                "random_seed": 0,
            },
            code_version="test-sha",
            dependencies_lock="test-lock",
            git_status_clean=True,
            as_of_timestamp=dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
            data_provider="yfinance",
        )
        session.add(job)
        session.flush()
        return job.id


def test_run_backtest_job_persists_result(
    migrated_database: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(tasks, "get_strategy", lambda strategy_id: WorkerTestStrategy)
    monkeypatch.setattr(tasks, "get_data_source", lambda provider: _worker_source())
    job_id = _seed_worker_job()

    tasks.run_backtest_job(str(job_id))

    with sync_session() as session:
        job = (
            session.execute(
                text(
                    "SELECT status, started_at, completed_at, error_message "
                    "FROM jobs WHERE id = :job_id"
                ),
                {"job_id": job_id},
            )
            .mappings()
            .one()
        )
        result = (
            session.execute(
                text(
                    "SELECT summary, equity_curve, holdings, trades "
                    "FROM backtest_results WHERE job_id = :job_id"
                ),
                {"job_id": job_id},
            )
            .mappings()
            .one()
        )

    assert job["status"] == "completed"
    assert job["started_at"] is not None
    assert job["completed_at"] is not None
    assert job["error_message"] is None
    assert result["summary"]["final_value"] > 0.0
    assert result["equity_curve"]
    assert result["holdings"]
    assert result["trades"]


def test_run_backtest_job_marks_failed_on_exception(
    migrated_database: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(tasks, "get_strategy", lambda strategy_id: WorkerTestStrategy)

    def _boom(provider: str) -> DataSource:
        raise RuntimeError(f"provider unavailable: {provider}")

    monkeypatch.setattr(tasks, "get_data_source", _boom)
    job_id = _seed_worker_job()

    with pytest.raises(RuntimeError, match="provider unavailable"):
        tasks.run_backtest_job(str(job_id))

    with sync_session() as session:
        job = (
            session.execute(
                text("SELECT status, completed_at, error_message FROM jobs WHERE id = :job_id"),
                {"job_id": job_id},
            )
            .mappings()
            .one()
        )
        result_count = session.execute(
            text("SELECT COUNT(*) FROM backtest_results WHERE job_id = :job_id"),
            {"job_id": job_id},
        ).scalar_one()

    assert job["status"] == "failed"
    assert job["completed_at"] is not None
    assert "provider unavailable" in job["error_message"]
    assert result_count == 0
