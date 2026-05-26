"""Read-only MLflow API service functions."""

from __future__ import annotations

import datetime as dt

from mlflow.entities import Run
from mlflow.tracking import MlflowClient

from azureus.api.schemas import MLRunDetail, MLRunSummary
from azureus.config import get_settings


class MLRunNotFoundError(Exception):
    """Requested MLflow run does not exist."""


def list_ml_runs(strategy_id: str | None = None, limit: int = 50) -> list[MLRunSummary]:
    """Return recent MLflow runs, optionally filtered by strategy id."""
    client = _client()
    filter_string = f"tags.strategy_id = '{strategy_id}'" if strategy_id else ""
    runs = client.search_runs(
        experiment_ids=["0"],
        filter_string=filter_string,
        max_results=limit,
        order_by=["attributes.start_time DESC"],
    )
    return [_summary_from_run(run) for run in runs]


def get_ml_run(run_id: str) -> MLRunDetail:
    """Return one MLflow run by id."""
    client = _client()
    try:
        run = client.get_run(run_id)
    except Exception as exc:
        raise MLRunNotFoundError(f"unknown MLflow run: {run_id}") from exc
    summary = _summary_from_run(run)
    return MLRunDetail(**summary.model_dump(), artifact_uri=run.info.artifact_uri)


def _client() -> MlflowClient:
    settings = get_settings()
    return MlflowClient(tracking_uri=settings.mlflow_tracking_uri)


def _summary_from_run(run: Run) -> MLRunSummary:
    tags = dict(run.data.tags)
    return MLRunSummary(
        run_id=run.info.run_id,
        strategy_id=tags.get("strategy_id"),
        status=run.info.status,
        start_time=_millis_to_datetime(run.info.start_time),
        end_time=_millis_to_datetime(run.info.end_time),
        metrics=dict(run.data.metrics),
        params=dict(run.data.params),
        tags=tags,
    )


def _millis_to_datetime(value: int | None) -> dt.datetime | None:
    if value is None:
        return None
    return dt.datetime.fromtimestamp(value / 1000, tz=dt.UTC)
