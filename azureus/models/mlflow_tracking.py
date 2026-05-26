"""Small MLflow logging wrapper used by Strategy 2."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import mlflow
import mlflow.lightgbm

from azureus.config import get_settings

logger = logging.getLogger(__name__)


def log_gbm_window_run(
    *,
    strategy_id: str,
    window_id: str,
    model: object,
    params: Mapping[str, Any],
    metrics: Mapping[str, float],
    tags: Mapping[str, str],
) -> str | None:
    """Log one Strategy 2 walk-forward window to MLflow.

    Logging failures should not break a public backtest. The job still
    carries diagnostics; the missing run id makes the MLflow gap explicit.
    """
    try:
        settings = get_settings()
        mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
        mlflow.set_experiment("azureus_strategy2")
        with mlflow.start_run(run_name=f"{strategy_id}:{window_id}") as run:
            mlflow.set_tags({"strategy_id": strategy_id, "window_id": window_id, **dict(tags)})
            mlflow.log_params({key: _stringify(value) for key, value in params.items()})
            mlflow.log_metrics(dict(metrics))
            mlflow.lightgbm.log_model(model, name="model")
            return str(run.info.run_id)
    except Exception:
        logger.exception("MLflow logging failed for %s/%s", strategy_id, window_id)
        return None


def _stringify(value: Any) -> str:
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    return repr(value)
