"""ML API service tests."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from azureus.api.services import ml


@dataclass(frozen=True)
class FakeExperiment:
    """Minimal MLflow experiment double."""

    experiment_id: str


@dataclass(frozen=True)
class FakeRunInfo:
    """Minimal MLflow run info double."""

    run_id: str
    status: str
    start_time: int
    end_time: int | None
    artifact_uri: str = ""


@dataclass(frozen=True)
class FakeRunData:
    """Minimal MLflow run data double."""

    tags: dict[str, str]
    metrics: dict[str, float]
    params: dict[str, str]


@dataclass(frozen=True)
class FakeRun:
    """Minimal MLflow run double."""

    info: FakeRunInfo
    data: FakeRunData


class FakeClient:
    """MLflow client double that records searched experiment ids."""

    def __init__(self) -> None:
        self.searched_experiment_ids: list[str] | None = None
        self.filter_string: str | None = None

    def search_experiments(self) -> list[FakeExperiment]:
        return [FakeExperiment("0"), FakeExperiment("42")]

    def search_runs(
        self,
        experiment_ids: list[str],
        filter_string: str,
        max_results: int,
        order_by: list[str],
    ) -> list[FakeRun]:
        self.searched_experiment_ids = experiment_ids
        self.filter_string = filter_string
        assert max_results == 10
        assert order_by == ["attributes.start_time DESC"]
        return [
            FakeRun(
                info=FakeRunInfo(
                    run_id="run_123",
                    status="FINISHED",
                    start_time=1_700_000_000_000,
                    end_time=None,
                ),
                data=FakeRunData(
                    tags={"strategy_id": "gbm_factors_v1"},
                    metrics={"mean_ic": 0.1},
                    params={"cv_folds": "2"},
                ),
            )
        ]


def test_list_ml_runs_searches_all_active_experiments(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strategy 2 runs should not disappear outside MLflow's default experiment."""
    client = FakeClient()
    monkeypatch.setattr(ml, "_client", lambda: client)

    runs = ml.list_ml_runs(strategy_id="gbm_factors_v1", limit=10)

    assert client.searched_experiment_ids == ["0", "42"]
    assert client.filter_string == "tags.strategy_id = 'gbm_factors_v1'"
    assert [run.run_id for run in runs] == ["run_123"]
    assert runs[0].strategy_id == "gbm_factors_v1"
    assert runs[0].metrics == {"mean_ic": 0.1}
