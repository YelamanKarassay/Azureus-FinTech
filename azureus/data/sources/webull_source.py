"""Webull HK market-data ingestion helpers for the public price path."""

from __future__ import annotations

import datetime as dt
import logging
import os
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import pandas as pd

logger = logging.getLogger(__name__)

PROVIDER_NAME = "webull"
DEFAULT_WEBULL_START = dt.date(2018, 1, 1)
DEFAULT_WEBULL_CATEGORY = "HK_STOCK"
DEFAULT_WEBULL_TIMESPAN = "D"
DEFAULT_WEBULL_COUNT = "1200"
HK_TZ = ZoneInfo("Asia/Hong_Kong")

_PRICE_COLUMNS = [
    "provider",
    "ticker",
    "date",
    "open",
    "high",
    "low",
    "close",
    "adjusted_close",
    "volume",
]


@dataclass(frozen=True)
class WebullDownloadSpec:
    """One Webull historical-bar request specification."""

    canonical_symbol: str
    webull_symbol: str
    category: str
    timespan: str
    start: dt.date
    end: dt.date


def fetch_prices_from_webull(
    ticker: str,
    start: dt.date,
    end: dt.date,
    *,
    data_client: Any | None = None,
    category: str = DEFAULT_WEBULL_CATEGORY,
    timespan: str = DEFAULT_WEBULL_TIMESPAN,
    count: str = DEFAULT_WEBULL_COUNT,
    sleep_seconds: float = 1.05,
) -> pd.DataFrame:
    """Fetch daily Webull bars and normalize them to the prices table shape."""
    client = data_client or build_webull_client()
    spec = WebullDownloadSpec(
        canonical_symbol=ticker,
        webull_symbol=to_webull_hk_symbol(ticker),
        category=category,
        timespan=timespan,
        start=start,
        end=end,
    )
    bars = download_bars(client, spec, count=count, sleep_seconds=sleep_seconds)
    if bars.empty:
        return _empty_prices_frame()

    frame = bars.rename(columns={"symbol": "ticker", "timestamp": "date"}).copy()
    frame["provider"] = PROVIDER_NAME
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce").dt.normalize()
    frame["adjusted_close"] = pd.NA
    frame["volume"] = pd.to_numeric(frame["volume"], errors="coerce").round().astype("Int64")
    for column in ["open", "high", "low", "close", "adjusted_close"]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.dropna(subset=["date", "close"]).reset_index(drop=True)
    return frame[_PRICE_COLUMNS]


def download_bars(
    data_client: Any,
    spec: WebullDownloadSpec,
    *,
    count: str = DEFAULT_WEBULL_COUNT,
    sleep_seconds: float = 1.05,
) -> pd.DataFrame:
    """Download all bars for one spec, paginating backward from `end`."""
    start_dt = dt.datetime.combine(spec.start, dt.time.min, tzinfo=HK_TZ)
    cursor = dt.datetime.combine(spec.end, dt.time.max, tzinfo=HK_TZ)
    frames: list[pd.DataFrame] = []
    seen_oldest: set[pd.Timestamp] = set()

    while cursor >= start_dt:
        response = get_history_bar_with_retry(data_client, spec, count=count, cursor=cursor)
        if response.status_code != 200:
            raise RuntimeError(f"{spec.canonical_symbol} returned HTTP {response.status_code}")
        payload = response.json()
        if not payload:
            break
        frame = normalize_webull_bars(payload, spec.canonical_symbol, spec.timespan)
        if frame.empty:
            break
        frames.append(frame)
        oldest = pd.to_datetime(frame["timestamp"]).min().tz_localize(HK_TZ)
        if oldest in seen_oldest or oldest <= start_dt:
            break
        seen_oldest.add(oldest)
        cursor = oldest.to_pydatetime() - pd.Timedelta(milliseconds=1)
        time.sleep(sleep_seconds)

    if not frames:
        return pd.DataFrame(
            columns=["symbol", "timestamp", "open", "high", "low", "close", "volume"]
        )

    out = pd.concat(frames, ignore_index=True)
    out = out.drop_duplicates(["symbol", "timestamp"]).sort_values("timestamp")
    dates = pd.to_datetime(out["timestamp"]).dt.date
    out = out[(dates >= spec.start) & (dates <= spec.end)]
    return out.reset_index(drop=True)


def get_history_bar_with_retry(
    data_client: Any,
    spec: WebullDownloadSpec,
    *,
    count: str,
    cursor: dt.datetime,
    max_attempts: int = 6,
) -> Any:
    """Fetch one Webull history page with bounded backoff on throttling."""
    for attempt in range(max_attempts):
        try:
            return data_client.market_data.get_history_bar(
                spec.webull_symbol,
                spec.category,
                spec.timespan,
                count=count,
                end_time=_millis(cursor),
            )
        except Exception as exc:
            text = str(exc)
            retryable = "429" in text or "TOO_MANY_REQUESTS" in text or "too many requests" in text
            if not retryable or attempt == max_attempts - 1:
                raise
            delay = min(45.0, 5.0 * (attempt + 1))
            logger.warning(
                "Webull throttled %s; sleeping %.0fs before retry %d/%d",
                spec.canonical_symbol,
                delay,
                attempt + 2,
                max_attempts,
            )
            time.sleep(delay)
    raise RuntimeError("unreachable Webull retry loop exit")


def normalize_webull_bars(
    payload: list[dict[str, Any]],
    canonical_symbol: str,
    timespan: str,
) -> pd.DataFrame:
    """Normalize Webull bar JSON into timestamped OHLCV rows."""
    frame = pd.DataFrame(payload).rename(columns={"time": "timestamp"})
    if frame.empty:
        return pd.DataFrame(
            columns=["symbol", "timestamp", "open", "high", "low", "close", "volume"]
        )
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="coerce")
    frame["timestamp"] = frame["timestamp"].dt.tz_convert(HK_TZ)
    shift = _timespan_delta(timespan)
    if shift is not None:
        frame["timestamp"] = frame["timestamp"] + shift
    frame["timestamp"] = frame["timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S")
    frame["symbol"] = canonical_symbol
    for column in ["open", "high", "low", "close", "volume"]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    columns = ["symbol", "timestamp", "open", "high", "low", "close", "volume"]
    return frame[columns].dropna().sort_values("timestamp").reset_index(drop=True)


def build_webull_client(endpoint: str | None = None) -> Any:
    """Build an authenticated Webull SDK data client from environment secrets."""
    try:
        from webull.core.client import ApiClient
        from webull.data.data_client import DataClient
    except ImportError as exc:  # pragma: no cover - dependency presence is CI/package level.
        raise RuntimeError("Install webull-openapi-python-sdk to use Webull ingestion") from exc

    app_key = os.environ.get("WEBULL_APP_KEY")
    app_secret = os.environ.get("WEBULL_APP_SECRET")
    if not app_key or not app_secret:
        raise RuntimeError("WEBULL_APP_KEY and WEBULL_APP_SECRET must be set")

    api_client = ApiClient(app_key, app_secret, "hk")
    api_client.add_endpoint(
        "hk",
        _normalize_endpoint(
            endpoint or os.environ.get("WEBULL_API_ENDPOINT", "api.sandbox.webull.hk")
        ),
    )
    return DataClient(api_client)


def to_webull_hk_symbol(symbol: str) -> str:
    """Map canonical HK tickers like `0700.HK` to Webull's five-digit code."""
    root = symbol.upper().removesuffix(".HK").removeprefix("HK.")
    if root.isdigit():
        return root.zfill(5)
    return symbol


def _empty_prices_frame() -> pd.DataFrame:
    return pd.DataFrame({column: [] for column in _PRICE_COLUMNS}).astype(
        {
            "provider": "string",
            "ticker": "string",
            "date": "datetime64[ns]",
            "open": "float64",
            "high": "float64",
            "low": "float64",
            "close": "float64",
            "adjusted_close": "float64",
            "volume": "Int64",
        }
    )


def _timespan_delta(timespan: str) -> pd.Timedelta | None:
    upper = timespan.upper()
    if upper.startswith("M") and upper[1:].isdigit():
        return pd.Timedelta(minutes=int(upper[1:]))
    if upper.startswith("S") and upper[1:].isdigit():
        return pd.Timedelta(seconds=int(upper[1:]))
    return None


def _millis(value: dt.datetime) -> int:
    return int(value.timestamp() * 1000)


def _normalize_endpoint(endpoint: str) -> str:
    parsed = urlparse(endpoint.strip().rstrip("/"))
    return parsed.netloc or endpoint
