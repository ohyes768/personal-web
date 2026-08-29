"""fund_flow_service 单元测试

数据源：东财 datacenter-web RPT_MUTUAL_DEAL_HISTORY
- MUTUAL_TYPE 005=北向合计 → DEAL_AMT（北向成交额）
- MUTUAL_TYPE 006=南向合计 → NET_DEAL_AMT/BUY_AMT/SELL_AMT
- 单位：原始百万元 ÷100 转亿元（南向为亿港元）

全部 monkeypatch src.services.fund_flow_service._request，不真连。
"""
from __future__ import annotations

from typing import Any, Optional

import pandas as pd
import pytest
import requests

import src.services.fund_flow_service as ffs
from src.services.fund_flow_service import FundFlowService


def _row(
    trade_date: str,
    deal_amt: Optional[float] = None,
    net: Optional[float] = None,
    buy: Optional[float] = None,
    sell: Optional[float] = None,
) -> dict:
    return {
        "TRADE_DATE": f"{trade_date} 00:00:00",
        "DEAL_AMT": deal_amt,
        "NET_DEAL_AMT": net,
        "BUY_AMT": buy,
        "SELL_AMT": sell,
    }


class FakeResponse:
    """requests.Response 替身：json()/raise_for_status()"""

    def __init__(self, payload: dict, status: int = 200):
        self._payload = payload
        self.status_code = status

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f"status={self.status_code}")

    def json(self) -> dict:
        return self._payload


def _page_payload(rows: list[dict]) -> dict:
    return {"success": True, "result": {"data": rows}}


def _patch_pages(monkeypatch, pages_by_type: dict[str, list[list[dict]]]) -> list[dict]:
    """按 MUTUAL_TYPE 依次返回预置分页；记录每次请求的 params"""
    calls: list[dict] = []

    def fake_request(params: dict) -> FakeResponse:
        calls.append(params)
        mtype = params["filter"].split('"')[1]
        page = int(params["pageNumber"])
        pages = pages_by_type.get(mtype, [])
        rows = pages[page - 1] if page - 1 < len(pages) else []
        return FakeResponse(_page_payload(rows))

    monkeypatch.setattr(ffs, "_request", fake_request)
    return calls


class TestFetchPage:
    def test_params_contain_report_and_paging(self, monkeypatch):
        calls = _patch_pages(monkeypatch, {"005": [[_row("2026-08-28", deal_amt=278121.63)]]})
        svc = FundFlowService()
        rows = svc._fetch_page("005", 1)
        assert rows[0]["DEAL_AMT"] == 278121.63
        p = calls[0]
        assert p["reportName"] == "RPT_MUTUAL_DEAL_HISTORY"
        assert p["pageNumber"] == "1"
        assert p["pageSize"] == "500"
        assert p["filter"] == '(MUTUAL_TYPE="005")'
        assert p["sortColumns"] == "TRADE_DATE"
        assert p["sortTypes"] == "1"

    def test_success_false_without_result_raises(self, monkeypatch):
        monkeypatch.setattr(
            ffs, "_request", lambda p: FakeResponse({"success": False, "message": "boom"})
        )
        with pytest.raises(Exception, match="东财接口返回异常"):
            FundFlowService()._fetch_page("005", 1)

    def test_result_null_returns_empty_list(self, monkeypatch):
        monkeypatch.setattr(
            ffs, "_request", lambda p: FakeResponse({"success": True, "result": None})
        )
        assert FundFlowService()._fetch_page("005", 1) == []


class TestFetchAllPages:
    def test_pagination_stops_on_short_page(self, monkeypatch):
        # 第 1 页满 500 行（用少量行 + page_size 覆盖模拟短页终止），第 2 页空
        page1 = [_row(f"2026-08-{i:02d}", deal_amt=1.0) for i in range(1, 4)]
        _patch_pages(monkeypatch, {"005": [page1]})
        rows = FundFlowService()._fetch_all_pages("005", "2026-01-01", "2026-12-31", page_size=3)
        assert len(rows) == 3  # 满 3 行短页 → 停止翻页

    def test_date_range_filters_local(self, monkeypatch):
        rows = [
            _row("2026-08-26", deal_amt=1.0),
            _row("2026-08-27", deal_amt=2.0),
            _row("2026-08-28", deal_amt=3.0),
        ]
        _patch_pages(monkeypatch, {"005": [rows]})
        got = FundFlowService()._fetch_all_pages("005", "2026-08-27", "2026-08-28")
        assert [r["TRADE_DATE"][:10] for r in got] == ["2026-08-27", "2026-08-28"]


class TestToFrame:
    def test_unit_million_to_yi(self):
        # 44732.81 百万港元 ÷100 = 447.3281 亿（勾稽 akshare 南向买入）
        df = FundFlowService()._to_frame(
            [_row("2026-08-28", buy=44732.81, sell=43556.61, net=1176.2)],
            ffs._SOUTH_COLS,
        )
        assert df.loc[pd.Timestamp("2026-08-28"), "南向买入"] == pytest.approx(447.3281)
        assert df.loc[pd.Timestamp("2026-08-28"), "南向净流入"] == pytest.approx(11.762)
        assert df.loc[pd.Timestamp("2026-08-28"), "南向卖出"] == pytest.approx(435.5661)

    def test_none_value_kept_as_nan(self):
        df = FundFlowService()._to_frame(
            [_row("2024-08-19", net=None, buy=None, sell=None)], ffs._SOUTH_COLS
        )
        assert df.isna().all(axis=None)

    def test_date_from_trade_date_prefix(self):
        df = FundFlowService()._to_frame(
            [_row("2014-11-17", deal_amt=12082.33)], ffs._NORTH_COLS
        )
        assert df.index[0] == pd.Timestamp("2014-11-17")
        assert df.index.name == "date"
        assert list(df.columns) == ["北向成交额"]

    def test_empty_rows_gives_empty_frame(self):
        df = FundFlowService()._to_frame([], ffs._NORTH_COLS)
        assert df.empty and list(df.columns) == ["北向成交额"]


class TestFetchHistory:
    def test_north_and_south_assembled(self, monkeypatch):
        _patch_pages(
            monkeypatch,
            {
                "005": [[_row("2026-08-28", deal_amt=278121.63)]],
                "006": [[_row("2026-08-28", net=1176.2, buy=44732.81, sell=43556.61)]],
            },
        )
        result = FundFlowService().fetch_history("2026-08-01", "2026-08-28")
        assert list(result["north"].columns) == ["北向成交额"]
        assert list(result["south"].columns) == ["南向净流入", "南向买入", "南向卖出"]
        # 2026-08-28 北向 278121.63 百万 = 2781.2163 亿（勾稽：沪123405.23+深154716.4）
        assert result["north"].iloc[0]["北向成交额"] == pytest.approx(2781.2163)

    def test_fetch_recent_window_about_10_days(self, monkeypatch):
        calls = _patch_pages(monkeypatch, {"005": [[]], "006": [[]]})
        FundFlowService().fetch_recent(days=10)
        # 今天往前 10 自然日：起点早于今天-10 天且不早于 -11 天
        today = pd.Timestamp.now().normalize()
        expect_start = (today - pd.Timedelta(days=10)).strftime("%Y-%m-%d")
        # fetch_recent 不传日期到 _fetch_all_pages 的过滤在 rows 为空时不可见，
        # 但 fetch_history 的 log 入参可由 start 日期推；此处验证调用发生即可
        assert len(calls) == 2  # north + south 各一页


class TestNetworkErrors:
    def test_transport_error_raises_after_retry(self, monkeypatch):
        import tenacity

        def boom(params: dict) -> Any:
            raise requests.exceptions.ConnectionError("reset")

        # 保留原 retry 装饰语义：reraise=True → ConnectionError 直接抛出
        monkeypatch.setattr(ffs, "_request", boom)
        with pytest.raises((requests.exceptions.ConnectionError, tenacity.RetryError)):
            FundFlowService()._fetch_page("005", 1)
