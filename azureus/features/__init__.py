"""Feature engineering — feature protocol, registry, and built-in catalog."""

from azureus.features.base import Feature
from azureus.features.fundamentals import (
    accruals,
    book_to_price,
    debt_to_equity,
    earnings_yield,
    fcf_to_price,
    gross_profitability,
    roe,
    sales_to_price,
)

# Import modules with registration side effects.
from azureus.features.market import beta_252d, momentum_12_1, realized_vol_252d
from azureus.features.registry import get_feature, list_features, register

__all__ = [
    "Feature",
    "accruals",
    "beta_252d",
    "book_to_price",
    "debt_to_equity",
    "earnings_yield",
    "fcf_to_price",
    "get_feature",
    "gross_profitability",
    "list_features",
    "momentum_12_1",
    "realized_vol_252d",
    "roe",
    "sales_to_price",
    "register",
]
