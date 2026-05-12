"""FastAPI application entry point.

Exposes the minimum endpoints required by the Phase 0 success criterion:
`/api/v1/health` and `/api/v1/version`. Additional routes are mounted from
`azureus.api.routes` in later phases.
"""

from __future__ import annotations

import os

from fastapi import FastAPI
from pydantic import BaseModel

from azureus import __version__

app = FastAPI(
    title="Azureus API",
    version=__version__,
    docs_url="/api/v1/docs",
    redoc_url="/api/v1/redoc",
    openapi_url="/api/v1/openapi.json",
)


class HealthResponse(BaseModel):
    """Liveness response payload."""

    status: str
    version: str


class VersionResponse(BaseModel):
    """Build-metadata response payload."""

    version: str
    git_sha: str | None
    build_time: str | None


@app.get("/api/v1/health", response_model=HealthResponse, tags=["operational"])
def health() -> HealthResponse:
    """Liveness probe. Returns 200 with the running package version."""
    return HealthResponse(status="ok", version=__version__)


@app.get("/api/v1/version", response_model=VersionResponse, tags=["operational"])
def version() -> VersionResponse:
    """Return build metadata captured at container build time."""
    return VersionResponse(
        version=__version__,
        git_sha=os.environ.get("GIT_SHA"),
        build_time=os.environ.get("BUILD_TIME"),
    )
