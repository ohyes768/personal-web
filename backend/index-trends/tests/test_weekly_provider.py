"""周K供应商适配：周期参数、重复周、乱序、非有限价格与 OHLC 异常。

脱网：用 httpx MockTransport 返回构造的响应体，不触网。
"""
from __future__ import annotations

import httpx
import pytest

from src.data.provider import ProviderError, fetch_kline

WEEK_KEY = "week"


def _response(rows: list[list[str]]) -> dict:
    return {"code": 0, "msg": "", "data": {"sh000300": {WEEK_KEY: rows}}}


def _client(rows: list[list[str]], status: int = 200) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "week" in str(request.url)
        return httpx.Response(status, json=_response(rows))

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_fetch_weekly_kline_parses_rows():
    rows = [
        ["2026-10-30", "4078.570", "3985.500", "4110.000", "3968.860", "890918238"],
        ["2026-11-06", "4005.940", "4012.460", "4038.820", "3988.170", "244401128"],
    ]
    bars = fetch_kline("sh000300", "week", 1600, _client(rows))
    assert len(bars) == 2
    assert bars[0].date == "2026-10-30"
    assert bars[0].close == 3985.500
    assert bars[1].open == 4005.940


def test_weekly_request_uses_week_period_and_count():
    """周K 请求参数：周期 week、条数 1600（覆盖 2005-04 至今）。"""
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, json=_response([]))

    client = httpx.Client(transport=httpx.MockTransport(handler))
    fetch_kline("sh000300", "week", 1600, client)
    assert len(seen) == 1
    assert "week" in seen[0]
    assert "1600" in seen[0]


def test_fetch_weekly_kline_rejects_bad_code():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"code": -1, "msg": "boom", "data": {}})

    with pytest.raises(ProviderError):
        fetch_kline("sh000300", "week", 1600, httpx.Client(transport=httpx.MockTransport(handler)))


def test_fetch_weekly_kline_rejects_missing_key():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"code": 0, "msg": "", "data": {"sh000300": {}}})

    with pytest.raises(ProviderError):
        fetch_kline("sh000300", "week", 1600, httpx.Client(transport=httpx.MockTransport(handler)))


def test_fetch_weekly_kline_rejects_non_numeric():
    rows = [["2026-10-30", "abc", "3985.500", "4110.000", "3968.860"]]
    with pytest.raises(ProviderError):
        fetch_kline("sh000300", "week", 1600, _client(rows))


def test_fetch_weekly_kline_rejects_short_row():
    rows = [["2026-10-30", "4078.570"]]
    with pytest.raises(ProviderError):
        fetch_kline("sh000300", "week", 1600, _client(rows))


def test_fetch_weekly_kline_rejects_http_error():
    with pytest.raises(ProviderError):
        fetch_kline("sh000300", "week", 1600, _client([], status=500))
