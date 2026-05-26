"""API catalog endpoint tests."""

from __future__ import annotations

from fastapi.testclient import TestClient

from azureus.api.main import app
from azureus.strategies.gbm_factors_v1 import GBMFactorsV1Strategy
from azureus.strategies.multi_factor_v1 import MultiFactorV1Strategy


def test_strategy_catalog_lists_registered_strategies() -> None:
    client = TestClient(app)

    response = client.get("/api/v1/strategies")

    assert response.status_code == 200
    strategy_ids = {item["id"] for item in response.json()}
    assert "benchmark_equal_weight_hsi" in strategy_ids
    assert GBMFactorsV1Strategy.id in strategy_ids
    assert MultiFactorV1Strategy.id in strategy_ids


def test_strategy_params_schema_is_served() -> None:
    client = TestClient(app)

    response = client.get(f"/api/v1/strategies/{MultiFactorV1Strategy.id}/params-schema")

    assert response.status_code == 200
    schema = response.json()
    assert schema["title"] == "MultiFactorV1Params"
    assert "n_long" in schema["properties"]

    strategy2_response = client.get(f"/api/v1/strategies/{GBMFactorsV1Strategy.id}/params-schema")
    assert strategy2_response.status_code == 200
    strategy2_schema = strategy2_response.json()
    assert strategy2_schema["title"] == "GBMFactorsV1Params"
    assert "training_warmup_years" in strategy2_schema["properties"]


def test_feature_catalog_lists_registered_features() -> None:
    client = TestClient(app)

    response = client.get("/api/v1/features")

    assert response.status_code == 200
    feature_names = {item["name"] for item in response.json()}
    assert {"earnings_yield", "momentum_12_1", "beta_252d"} <= feature_names


def test_unknown_catalog_items_return_404() -> None:
    client = TestClient(app)

    strategy_response = client.get("/api/v1/strategies/not-a-strategy")
    feature_response = client.get("/api/v1/features/not-a-feature")

    assert strategy_response.status_code == 404
    assert feature_response.status_code == 404
