"""Hybrid public data provider: Webull prices plus yfinance fundamentals."""

from __future__ import annotations

from azureus.data.sources.webull_source import PROVIDER_NAME as WEBULL_PROVIDER_NAME
from azureus.data.sources.yfinance_source import PROVIDER_NAME as YFINANCE_PROVIDER_NAME
from azureus.data.sources.yfinance_source import YFinanceDataSource

PROVIDER_NAME = "public_free"


class PublicFreeDataSource(YFinanceDataSource):
    """Read DB-backed public demo data from its constituent provider tables.

    The job-level provider is `public_free` for reproducibility, while the
    underlying price rows remain `provider='webull'` and fundamentals remain
    `provider='yfinance'`.
    """

    provider_name = PROVIDER_NAME
    price_provider_name = WEBULL_PROVIDER_NAME
    fundamentals_provider_name = YFINANCE_PROVIDER_NAME
