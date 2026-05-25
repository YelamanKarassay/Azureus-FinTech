"""DataSource factory for provider-selected jobs."""

from __future__ import annotations

from azureus.data.sources.base import DataSource
from azureus.data.sources.yfinance_source import PROVIDER_NAME, YFinanceDataSource

_SUPPORTED_PROVIDERS = frozenset({PROVIDER_NAME})


def get_data_source(provider: str) -> DataSource:
    """Build a concrete `DataSource` for a required provider name."""
    if provider == PROVIDER_NAME:
        return YFinanceDataSource()
    raise ValueError(f"unsupported data provider: {provider}")


def list_supported_providers() -> list[str]:
    """Provider names available in this runtime."""
    return sorted(_SUPPORTED_PROVIDERS)
