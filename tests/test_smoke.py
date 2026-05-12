"""Smoke tests — package imports and the API boots end-to-end in-process."""

from __future__ import annotations

from fastapi.testclient import TestClient

import azureus
from azureus.api.main import app


def test_package_version() -> None:
    assert azureus.__version__ == "0.0.1"


def test_health_endpoint_returns_ok() -> None:
    client = TestClient(app)
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"] == azureus.__version__


def test_version_endpoint_includes_version() -> None:
    client = TestClient(app)
    response = client.get("/api/v1/version")

    assert response.status_code == 200
    assert response.json()["version"] == azureus.__version__


def test_openapi_schema_is_served() -> None:
    client = TestClient(app)
    response = client.get("/api/v1/openapi.json")
    assert response.status_code == 200
