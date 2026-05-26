"""Pydantic request/response schemas for the public API."""

from __future__ import annotations

import datetime as dt
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class _APIModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class StrategySummary(_APIModel):
    """Registered strategy metadata."""

    id: str
    name: str
    description: str


class StrategyDetail(StrategySummary):
    """Registered strategy metadata plus parameter schema."""

    params_schema: dict[str, Any]


class FeatureSummary(_APIModel):
    """Registered feature metadata."""

    name: str
    description: str
    family: str
    requires_metrics: list[str]
    requires_lookback_days: int


class BacktestCreateRequest(_APIModel):
    """Create an asynchronous backtest job."""

    strategy_id: str = Field(min_length=1)
    params: dict[str, Any] = Field(default_factory=dict)
    start: dt.date
    end: dt.date
    initial_capital: float = Field(default=1_000_000.0, gt=0.0)
    data_provider: Literal["yfinance", "public_free"]
    random_seed: int = Field(default=0, ge=0)

    @field_validator("params")
    @classmethod
    def _copy_params(cls, value: dict[str, Any]) -> dict[str, Any]:
        return dict(value)

    @model_validator(mode="after")
    def _validate_date_range(self) -> BacktestCreateRequest:
        if self.end < self.start:
            raise ValueError("end must be on or after start")
        return self


class BacktestCreateResponse(_APIModel):
    """Queued backtest job response."""

    job_id: UUID
    status: str


class BacktestStatusResponse(_APIModel):
    """Durable backtest job status."""

    job_id: UUID
    strategy_id: str | None
    job_type: str
    status: str
    params: dict[str, Any]
    data_provider: str
    created_at: dt.datetime
    started_at: dt.datetime | None
    completed_at: dt.datetime | None
    error_message: str | None


class BacktestResultResponse(_APIModel):
    """Persisted backtest result payload."""

    job_id: UUID
    summary: dict[str, Any]
    equity_curve: list[dict[str, Any]]
    holdings: list[dict[str, Any]]
    trades: list[dict[str, Any]]
    diagnostics: dict[str, Any] | None = None


class MLRunSummary(_APIModel):
    """Read-only MLflow run summary exposed through the API."""

    run_id: str
    strategy_id: str | None = None
    status: str | None = None
    start_time: dt.datetime | None = None
    end_time: dt.datetime | None = None
    metrics: dict[str, float] = Field(default_factory=dict)
    params: dict[str, str] = Field(default_factory=dict)
    tags: dict[str, str] = Field(default_factory=dict)


class MLRunDetail(MLRunSummary):
    """Detailed read-only MLflow run metadata."""

    artifact_uri: str | None = None


class BacktestSeriesResponse(_APIModel):
    """One result table extracted from a persisted backtest result."""

    job_id: UUID
    rows: list[dict[str, Any]]
