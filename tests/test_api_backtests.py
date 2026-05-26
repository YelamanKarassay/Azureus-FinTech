"""Backtest API endpoint tests."""

from __future__ import annotations

from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import text

from azureus.api.main import app
from azureus.api.services import backtests as backtest_service
from azureus.data.db import sync_session
from azureus.data.models import BacktestResult


def _create_backtest(client: TestClient) -> UUID:
    response = client.post(
        "/api/v1/backtests",
        json={
            "strategy_id": "benchmark_equal_weight_hsi",
            "params": {},
            "start": "2024-01-02",
            "end": "2024-01-31",
            "initial_capital": 1_000_000.0,
            "data_provider": "yfinance",
            "random_seed": 123,
        },
    )
    assert response.status_code == 202
    return UUID(response.json()["job_id"])


def test_create_backtest_persists_job_and_enqueues(
    migrated_database: str,
    monkeypatch,
) -> None:
    enqueued: list[UUID] = []
    monkeypatch.setattr(backtest_service, "_enqueue_backtest_job", enqueued.append)

    with TestClient(app) as client:
        job_id = _create_backtest(client)

    assert enqueued == [job_id]
    with sync_session() as session:
        job = (
            session.execute(
                text(
                    "SELECT strategy_id, job_type, status, params, code_version, "
                    "dependencies_lock, git_status_clean, as_of_timestamp, data_provider "
                    "FROM jobs WHERE id = :job_id"
                ),
                {"job_id": job_id},
            )
            .mappings()
            .one()
        )
        strategy_count = session.execute(
            text("SELECT COUNT(*) FROM strategies WHERE id = 'benchmark_equal_weight_hsi'")
        ).scalar_one()

    assert strategy_count == 1
    assert job["strategy_id"] == "benchmark_equal_weight_hsi"
    assert job["job_type"] == "backtest"
    assert job["status"] == "queued"
    assert job["params"]["random_seed"] == 123
    assert job["params"]["strategy_params"]["universe_id"] == "HSI"
    assert job["code_version"]
    assert job["dependencies_lock"] is not None
    assert isinstance(job["git_status_clean"], bool)
    assert job["as_of_timestamp"] is not None
    assert job["data_provider"] == "yfinance"


def test_create_backtest_rejects_invalid_strategy_params(
    migrated_database: str,
    monkeypatch,
) -> None:
    enqueued: list[UUID] = []
    monkeypatch.setattr(backtest_service, "_enqueue_backtest_job", enqueued.append)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/backtests",
            json={
                "strategy_id": "multi_factor_v1",
                "params": {"n_long": 5},
                "start": "2024-01-02",
                "end": "2024-01-31",
                "initial_capital": 1_000_000.0,
                "data_provider": "yfinance",
            },
        )

    assert response.status_code == 422
    assert enqueued == []


def test_backtest_status_and_result_endpoints(
    migrated_database: str,
    monkeypatch,
) -> None:
    monkeypatch.setattr(backtest_service, "_enqueue_backtest_job", lambda job_id: None)

    with TestClient(app) as client:
        job_id = _create_backtest(client)

        status_response = client.get(f"/api/v1/backtests/{job_id}")
        not_ready_response = client.get(f"/api/v1/backtests/{job_id}/result")

        assert status_response.status_code == 200
        assert status_response.json()["status"] == "queued"
        assert not_ready_response.status_code == 409

        with sync_session() as session:
            session.add(
                BacktestResult(
                    job_id=job_id,
                    summary={"final_value": 1_010_000.0},
                    equity_curve=[{"date": "2024-01-02", "total_value": 1_010_000.0}],
                    holdings=[{"date": "2024-01-02", "ticker": "0700.HK", "weight": 1.0}],
                    trades=[{"ticker": "0700.HK", "shares": 100.0}],
                    diagnostics={"mean_ic": 0.05, "ic_series": []},
                )
            )

        result_response = client.get(f"/api/v1/backtests/{job_id}/result")
        equity_response = client.get(f"/api/v1/backtests/{job_id}/equity-curve")
        list_response = client.get("/api/v1/backtests")

        assert result_response.status_code == 200
        assert result_response.json()["summary"]["final_value"] == 1_010_000.0
        assert result_response.json()["diagnostics"]["mean_ic"] == 0.05
        assert equity_response.status_code == 200
        assert equity_response.json()["rows"][0]["total_value"] == 1_010_000.0
        assert list_response.status_code == 200
        assert list_response.json()[0]["job_id"] == str(job_id)


def test_create_backtest_accepts_public_free_provider(
    migrated_database: str,
    monkeypatch,
) -> None:
    enqueued: list[UUID] = []
    monkeypatch.setattr(backtest_service, "_enqueue_backtest_job", enqueued.append)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/backtests",
            json={
                "strategy_id": "gbm_factors_v1",
                "params": {},
                "start": "2018-01-01",
                "end": "2026-05-22",
                "initial_capital": 1_000_000.0,
                "data_provider": "public_free",
                "random_seed": 123,
            },
        )

    assert response.status_code == 202
    assert enqueued == [UUID(response.json()["job_id"])]


def test_unknown_backtest_returns_404(migrated_database: str) -> None:
    missing = "00000000-0000-0000-0000-000000000000"

    with TestClient(app) as client:
        response = client.get(f"/api/v1/backtests/{missing}")

    assert response.status_code == 404
