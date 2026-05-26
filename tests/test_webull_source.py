"""Webull ingestion helper tests."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import pandas as pd
import pytest

from azureus.data.sources import webull_source
from azureus.data.sources.webull_source import (
    WebullDownloadSpec,
    fetch_prices_from_webull,
    get_history_bar_with_retry,
    normalize_webull_bars,
    to_webull_hk_symbol,
)


@dataclass
class _Response:
    payload: list[dict[str, object]]
    status_code: int = 200

    def json(self) -> list[dict[str, object]]:
        return self.payload


class _MarketData:
    def __init__(self, responses: list[_Response]) -> None:
        self.responses = responses
        self.calls: list[dict[str, object]] = []

    def get_history_bar(
        self,
        symbol: str,
        category: str,
        timespan: str,
        *,
        count: str,
        end_time: int,
    ) -> _Response:
        self.calls.append(
            {
                "symbol": symbol,
                "category": category,
                "timespan": timespan,
                "count": count,
                "end_time": end_time,
            }
        )
        return self.responses.pop(0) if self.responses else _Response([])


class _Client:
    def __init__(self, responses: list[_Response]) -> None:
        self.market_data = _MarketData(responses)


def test_to_webull_hk_symbol_zero_pads_hk_codes() -> None:
    assert to_webull_hk_symbol("700.HK") == "00700"
    assert to_webull_hk_symbol("0700.HK") == "00700"
    assert to_webull_hk_symbol("HK.5") == "00005"


def test_normalize_webull_daily_bars() -> None:
    payload = [
        {
            "time": "2024-01-02T08:00:00Z",
            "open": "10",
            "high": "11",
            "low": "9",
            "close": "10.5",
            "volume": "1000",
        }
    ]

    df = normalize_webull_bars(payload, "0700.HK", "D")

    assert df.to_dict(orient="records") == [
        {
            "symbol": "0700.HK",
            "timestamp": "2024-01-02 16:00:00",
            "open": 10,
            "high": 11,
            "low": 9,
            "close": 10.5,
            "volume": 1000,
        }
    ]


def test_fetch_prices_from_webull_normalizes_to_price_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(webull_source, "time", type("T", (), {"sleep": lambda _seconds: None}))
    client = _Client(
        [
            _Response(
                [
                    {
                        "time": "2024-01-02T08:00:00Z",
                        "open": "10",
                        "high": "11",
                        "low": "9",
                        "close": "10.5",
                        "volume": "1000",
                    }
                ]
            ),
            _Response([]),
        ]
    )

    df = fetch_prices_from_webull(
        "0700.HK",
        dt.date(2024, 1, 1),
        dt.date(2024, 1, 31),
        data_client=client,
        sleep_seconds=0,
    )

    assert list(df.columns) == [
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
    assert df.loc[0, "provider"] == "webull"
    assert df.loc[0, "ticker"] == "0700.HK"
    assert df.loc[0, "date"] == pd.Timestamp("2024-01-02")
    assert pd.isna(df.loc[0, "adjusted_close"])


def test_webull_retry_backoff_does_not_leak_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    sleeps: list[float] = []
    monkeypatch.setattr(webull_source.time, "sleep", sleeps.append)

    class _RetryMarketData:
        def __init__(self) -> None:
            self.calls = 0

        def get_history_bar(self, *args: object, **kwargs: object) -> _Response:
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("429 TOO_MANY_REQUESTS")
            return _Response([])

    client = type("Client", (), {"market_data": _RetryMarketData()})()
    spec = WebullDownloadSpec(
        canonical_symbol="0700.HK",
        webull_symbol="00700",
        category="HK_STOCK",
        timespan="D",
        start=dt.date(2024, 1, 1),
        end=dt.date(2024, 1, 31),
    )

    response = get_history_bar_with_retry(
        client,
        spec,
        count="1200",
        cursor=dt.datetime(2024, 1, 31, tzinfo=dt.UTC),
    )

    assert response.status_code == 200
    assert sleeps == [5.0]
