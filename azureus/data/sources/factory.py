"""DataSource factory for provider-selected jobs."""

from __future__ import annotations

from azureus.data.sources.base import DataSource
from azureus.data.sources.public_free_source import PROVIDER_NAME as PUBLIC_FREE_PROVIDER_NAME
from azureus.data.sources.public_free_source import PublicFreeDataSource
from azureus.data.sources.yfinance_source import PROVIDER_NAME, YFinanceDataSource

_SUPPORTED_PROVIDERS = frozenset({PROVIDER_NAME, PUBLIC_FREE_PROVIDER_NAME})


def get_data_source(provider: str) -> DataSource:
    """Build a concrete `DataSource` for a required provider name."""
    if provider == PROVIDER_NAME:
        return YFinanceDataSource()
    if provider == PUBLIC_FREE_PROVIDER_NAME:
        return PublicFreeDataSource()
    raise ValueError(f"unsupported data provider: {provider}")


def list_supported_providers() -> list[str]:
    """Provider names available in this runtime."""
    return sorted(_SUPPORTED_PROVIDERS)
