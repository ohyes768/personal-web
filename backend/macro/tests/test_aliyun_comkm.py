"""阿里云 comkm 翻页：增量按 since 提前停；10 年上限不当 ERROR。"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import date, timedelta

os.environ.setdefault("FRED_API_KEY", "test-not-a-real-key")

import httpx
import pytest

from src.services.commodity_service import AliyunCommodityKlineClient
from src.services.index_service import AliyunIndexClient

PAGE_SIZE = 500


def _bars_newest_first(newest: date, n: int) -> list[dict]:
    """阿里云倒序：最新在前。"""
    rows: list[dict] = []
    d = newest
    for i in range(n):
        rows.append({"C": float(i + 1), "D": f"{d.isoformat()} 00:00:00"})
        d -= timedelta(days=1)
    return rows


def _client(cls, handler) -> object:
    obj = cls("test-appcode", "https://example.invalid")
    obj._client = httpx.AsyncClient(
        headers=obj._headers,
        timeout=30.0,
        transport=httpx.MockTransport(handler),
    )
    return obj


@pytest.mark.unit
def test_incremental_since_stops_after_page1():
    """since 落在第 1 页覆盖范围内时只打 1 次 HTTP，不翻到 10 年上限。"""
    calls: list[int] = []
    newest = date(2026, 8, 31)

    def handler(request: httpx.Request) -> httpx.Response:
        pidx = int(request.url.params["pidx"])
        calls.append(pidx)
        if pidx == 1:
            return httpx.Response(200, json={"Code": 0, "Msg": "", "Obj": _bars_newest_first(newest, PAGE_SIZE)})
        raise AssertionError(f"incremental 不应请求 pidx={pidx}")

    async def go():
        client = _client(AliyunIndexClient, handler)
        try:
            records = await client.fetch_klines("SPX", since=date(2026, 8, 29))
        finally:
            await client._client.aclose()
        return records

    records = asyncio.run(go())
    assert calls == [1]
    assert len(records) == PAGE_SIZE
    dates = [r["date"].date() for r in records]
    assert dates == sorted(dates)
    assert date(2026, 8, 31) in dates
    assert date(2026, 8, 29) in dates


@pytest.mark.unit
def test_history_without_since_paginates_until_short_page():
    """全量（since=None）仍翻到不足一页为止。"""
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        pidx = int(request.url.params["pidx"])
        calls.append(pidx)
        n = PAGE_SIZE if pidx < 3 else 12
        newest = date(2026, 8, 31) - timedelta(days=(pidx - 1) * PAGE_SIZE)
        return httpx.Response(200, json={"Code": 0, "Msg": "", "Obj": _bars_newest_first(newest, n)})

    async def go():
        client = _client(AliyunCommodityKlineClient, handler)
        try:
            records = await client.fetch_klines("SGEAU9999")
        finally:
            await client._client.aclose()
        return records

    records = asyncio.run(go())
    assert calls == [1, 2, 3]
    assert len(records) == PAGE_SIZE * 2 + 12


@pytest.mark.unit
def test_ten_year_cap_code_minus_100_is_end_not_error(caplog):
    """Code=-100（最多 10 年内）视为翻页结束，保留已拉到的数据，不打 ERROR。"""
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        pidx = int(request.url.params["pidx"])
        calls.append(pidx)
        if pidx == 1:
            return httpx.Response(
                200,
                json={"Code": 0, "Msg": "", "Obj": _bars_newest_first(date(2026, 8, 31), PAGE_SIZE)},
            )
        return httpx.Response(
            200,
            json={
                "Code": -100,
                "Msg": "日数据接口输出最多10年内,当前参数 页码15x页大小500(本次不计数)",
                "Obj": None,
            },
        )

    async def go():
        client = _client(AliyunIndexClient, handler)
        try:
            with caplog.at_level(logging.INFO):
                records = await client.fetch_klines("HKHSI")
        finally:
            await client._client.aclose()
        return records

    records = asyncio.run(go())
    assert calls == [1, 2]
    assert len(records) == PAGE_SIZE
    assert not any(r.levelno >= logging.ERROR for r in caplog.records)
    assert any("10年" in r.getMessage() or "-100" in r.getMessage() for r in caplog.records)
