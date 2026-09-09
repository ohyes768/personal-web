"""
market_size_fetcher 单测

覆盖：
  TestFetchSizeEastmoney — 东财 msm 单只（fallback 路径）
  TestFetchSizeXueqiu    — 雪球单只（主路径）
  TestFetchSize          — 雪球 → 东财 fallback 链
  TestFetchMarketSize    — 批量 fetch
"""
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.data.market_size_fetcher import (
    fetch_size,
    fetch_size_xq,
    fetch_size_eastmoney,
    fetch_market_size,
)


def _mock_response(datas: dict | None, status_code: int = 200) -> MagicMock:
    """构造 requests.get 的 mock 响应（东财）"""
    r = MagicMock()
    r.status_code = status_code
    r.raise_for_status = MagicMock()
    r.json.return_value = {"Datas": datas} if datas is not None else {}
    return r


def _mock_xueqiu_df(
    size: str | None = "39.38亿",
    estab: str | None = "2001-12-18",
    mgr: str | None = "华夏基金管理有限公司",
) -> pd.DataFrame:
    """构造雪球接口返回的 DataFrame（item/value 两列）"""
    items, values = [], []
    items.append("基金代码"); values.append("000001")
    items.append("基金名称"); values.append("测试基金")
    if size is not None:
        items.append("最新规模"); values.append(size)
    if estab is not None:
        items.append("成立时间"); values.append(estab)
    if mgr is not None:
        items.append("基金管理人"); values.append(mgr)
    return pd.DataFrame({"item": items, "value": values})


# ── 东财单只（fallback 路径）──────────────────────────────────


class TestFetchSizeEastmoney:
    """fetch_size_eastmoney 单只函数（fallback 路径）"""

    def test_parses_estabdate_and_endnav_and_jjgs(self):
        """完整字段：ESTABDATE / ENDNAV / JJGS 正确解析"""
        mock_resp = _mock_response({
            "ESTABDATE": "2019-04-03",
            "ENDNAV": 342743333.13,
            "JJGS": "中庚基金",
            "FSRQ": "2026-09-08",
        })
        with patch("src.data.market_size_fetcher.requests.get", return_value=mock_resp), \
             patch("src.data.market_size_fetcher.time.sleep"):
            result = fetch_size_eastmoney("007130", delay_s=0)

        assert result is not None
        assert result["code"] == "007130"
        assert result["established_date"].isoformat() == "2019-04-03"
        # 342743333.13 / 1e8 ≈ 3.4274
        assert result["size_yi"] == pytest.approx(3.4274, abs=1e-4)
        assert result["mgr_company"] == "中庚基金"

    def test_endnav_unit_division_by_1e8(self):
        """ENDNAV 单位换算：1e8 元 = 1 亿；5.5e8 元 = 5.5 亿"""
        r1 = _mock_response({"ENDNAV": 100000000.0})
        with patch("src.data.market_size_fetcher.requests.get", return_value=r1), \
             patch("src.data.market_size_fetcher.time.sleep"):
            assert fetch_size_eastmoney("000001", delay_s=0)["size_yi"] == 1.0

        r2 = _mock_response({"ENDNAV": 550000000.0})
        with patch("src.data.market_size_fetcher.requests.get", return_value=r2), \
             patch("src.data.market_size_fetcher.time.sleep"):
            assert fetch_size_eastmoney("000002", delay_s=0)["size_yi"] == 5.5

    def test_endnav_none_leaves_size_none(self):
        mock_resp = _mock_response({"ESTABDATE": "2020-01-01", "ENDNAV": None, "JJGS": "X"})
        with patch("src.data.market_size_fetcher.requests.get", return_value=mock_resp), \
             patch("src.data.market_size_fetcher.time.sleep"):
            result = fetch_size_eastmoney("000001", delay_s=0)
        assert result["size_yi"] is None
        assert result["established_date"].isoformat() == "2020-01-01"
        assert result["mgr_company"] == "X"

    def test_endnav_invalid_string_leaves_size_none(self):
        mock_resp = _mock_response({"ENDNAV": "abc"})
        with patch("src.data.market_size_fetcher.requests.get", return_value=mock_resp), \
             patch("src.data.market_size_fetcher.time.sleep"):
            assert fetch_size_eastmoney("000001", delay_s=0)["size_yi"] is None

    def test_jjgs_empty_string_becomes_none(self):
        mock_resp = _mock_response({"JJGS": ""})
        with patch("src.data.market_size_fetcher.requests.get", return_value=mock_resp), \
             patch("src.data.market_size_fetcher.time.sleep"):
            assert fetch_size_eastmoney("000001", delay_s=0)["mgr_company"] is None

    def test_jjgs_whitespace_only_becomes_none(self):
        mock_resp = _mock_response({"JJGS": "   "})
        with patch("src.data.market_size_fetcher.requests.get", return_value=mock_resp), \
             patch("src.data.market_size_fetcher.time.sleep"):
            assert fetch_size_eastmoney("000001", delay_s=0)["mgr_company"] is None

    def test_estabdate_missing_leaves_date_none(self):
        mock_resp = _mock_response({"ENDNAV": 100.0, "JJGS": "X"})
        with patch("src.data.market_size_fetcher.requests.get", return_value=mock_resp), \
             patch("src.data.market_size_fetcher.time.sleep"):
            result = fetch_size_eastmoney("000001", delay_s=0)
        assert result["established_date"] is None
        assert result["age_years"] is None

    def test_estabdate_short_string_ignored(self):
        mock_resp = _mock_response({"ESTABDATE": "2019", "ENDNAV": 100.0})
        with patch("src.data.market_size_fetcher.requests.get", return_value=mock_resp), \
             patch("src.data.market_size_fetcher.time.sleep"):
            result = fetch_size_eastmoney("000001", delay_s=0)
        assert result["established_date"] is None

    def test_estabdate_iso_with_extra_suffix(self):
        mock_resp = _mock_response({"ESTABDATE": "2019-04-03T00:00:00"})
        with patch("src.data.market_size_fetcher.requests.get", return_value=mock_resp), \
             patch("src.data.market_size_fetcher.time.sleep"):
            assert fetch_size_eastmoney("000001", delay_s=0)["established_date"].isoformat() == "2019-04-03"

    def test_datas_empty_returns_none(self):
        mock_resp = _mock_response({})
        with patch("src.data.market_size_fetcher.requests.get", return_value=mock_resp), \
             patch("src.data.market_size_fetcher.time.sleep"):
            assert fetch_size_eastmoney("000001", delay_s=0) is None

    def test_datas_key_missing_returns_none(self):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"foo": "bar"}
        with patch("src.data.market_size_fetcher.requests.get", return_value=mock_resp), \
             patch("src.data.market_size_fetcher.time.sleep"):
            assert fetch_size_eastmoney("000001", delay_s=0) is None

    def test_requests_exception_returns_none(self):
        with patch("src.data.market_size_fetcher.requests.get",
                    side_effect=ConnectionError("network error")), \
             patch("src.data.market_size_fetcher.time.sleep"):
            assert fetch_size_eastmoney("000001", delay_s=0) is None

    def test_http_status_error_returns_none(self):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = RuntimeError("404 Not Found")
        with patch("src.data.market_size_fetcher.requests.get", return_value=mock_resp), \
             patch("src.data.market_size_fetcher.time.sleep"):
            assert fetch_size_eastmoney("000001", delay_s=0) is None

    def test_invalid_json_returns_none(self):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.side_effect = ValueError("invalid json")
        with patch("src.data.market_size_fetcher.requests.get", return_value=mock_resp), \
             patch("src.data.market_size_fetcher.time.sleep"):
            assert fetch_size_eastmoney("000001", delay_s=0) is None

    def test_url_contains_code_and_platform_params(self):
        mock_resp = _mock_response({"ENDNAV": 1.0})
        with patch("src.data.market_size_fetcher.requests.get", return_value=mock_resp) as mock_get, \
             patch("src.data.market_size_fetcher.time.sleep"):
            fetch_size_eastmoney("007130", delay_s=0)
            called_url = mock_get.call_args[0][0]
            assert "FCODE=007130" in called_url
            assert "deviceid=W" in called_url
            assert "plat=Wap" in called_url
            assert "product=EFund" in called_url

    def test_user_agent_and_referer_headers_sent(self):
        """东财接口 Headers 含 User-Agent (iOS) / Referer"""
        mock_resp = _mock_response({"ENDNAV": 1.0})
        with patch("src.data.market_size_fetcher.requests.get", return_value=mock_resp) as mock_get, \
             patch("src.data.market_size_fetcher.time.sleep"):
            fetch_size_eastmoney("000001", delay_s=0)
            headers = mock_get.call_args.kwargs["headers"]
            assert "iPhone" in headers["User-Agent"]
            assert headers["Referer"] == "https://fund.eastmoney.com/"


# ── 雪球单只（主路径）──────────────────────────────────────


class TestFetchSizeXueqiu:
    """fetch_size_xq 单只函数（主路径）"""

    def test_parses_size_estabdate_and_mgr_company(self):
        """完整字段：最新规模/成立时间/基金管理人 正确解析"""
        import datetime
        df = _mock_xueqiu_df()
        with patch("src.data.market_size_fetcher.ak.fund_individual_basic_info_xq",
                    return_value=df), \
             patch("src.data.market_size_fetcher.time.sleep"):
            result = fetch_size_xq("000001", delay_s=0)

        assert result is not None
        assert result["code"] == "000001"
        assert result["size_yi"] == 39.38
        assert result["established_date"] == datetime.date(2001, 12, 18)
        assert result["mgr_company"] == "华夏基金管理有限公司"
        # 2001-12-18 到 today ≈ 24 年多
        assert result["age_years"] is not None and result["age_years"] > 24

    def test_size_in_wan_converts_to_yi(self):
        """'2250.45万' → 0.225045 亿"""
        df = _mock_xueqiu_df(size="2250.45万")
        with patch("src.data.market_size_fetcher.ak.fund_individual_basic_info_xq",
                    return_value=df), \
             patch("src.data.market_size_fetcher.time.sleep"):
            result = fetch_size_xq("000001", delay_s=0)
        assert result["size_yi"] == pytest.approx(0.2250, abs=1e-3)

    def test_size_in_yi_keeps_yi(self):
        """'39.38亿' → 39.38 亿（无需转换）"""
        df = _mock_xueqiu_df(size="39.38亿")
        with patch("src.data.market_size_fetcher.ak.fund_individual_basic_info_xq",
                    return_value=df), \
             patch("src.data.market_size_fetcher.time.sleep"):
            result = fetch_size_xq("000001", delay_s=0)
        assert result["size_yi"] == 39.38

    def test_size_without_unit_assumed_yi(self):
        """无单位数字直接当亿"""
        df = _mock_xueqiu_df(size="1234.56")
        with patch("src.data.market_size_fetcher.ak.fund_individual_basic_info_xq",
                    return_value=df), \
             patch("src.data.market_size_fetcher.time.sleep"):
            assert fetch_size_xq("000001", delay_s=0)["size_yi"] == 1234.56

    def test_size_invalid_string_returns_none_field(self):
        """size 解析失败 → 该字段 None，其他字段仍有效"""
        df = _mock_xueqiu_df(size="abc")
        with patch("src.data.market_size_fetcher.ak.fund_individual_basic_info_xq",
                    return_value=df), \
             patch("src.data.market_size_fetcher.time.sleep"):
            result = fetch_size_xq("000001", delay_s=0)
        assert result["size_yi"] is None
        assert result["established_date"] is not None  # 其他字段正常

    def test_estabdate_with_iso_suffix(self):
        """雪球返回 '2021-06-09T00:00:00' → 截前 10 位"""
        df = _mock_xueqiu_df(estab="2021-06-09T00:00:00")
        with patch("src.data.market_size_fetcher.ak.fund_individual_basic_info_xq",
                    return_value=df), \
             patch("src.data.market_size_fetcher.time.sleep"):
            result = fetch_size_xq("000001", delay_s=0)
        assert result["established_date"].isoformat() == "2021-06-09"

    def test_mgr_company_empty_becomes_none(self):
        df = _mock_xueqiu_df(mgr="   ")
        with patch("src.data.market_size_fetcher.ak.fund_individual_basic_info_xq",
                    return_value=df), \
             patch("src.data.market_size_fetcher.time.sleep"):
            assert fetch_size_xq("000001", delay_s=0)["mgr_company"] is None

    def test_key_error_returns_none(self):
        """雪球 KeyError 'data' → None（fallback 触发）"""
        with patch("src.data.market_size_fetcher.ak.fund_individual_basic_info_xq",
                    side_effect=KeyError("data")), \
             patch("src.data.market_size_fetcher.time.sleep"):
            assert fetch_size_xq("007130", delay_s=0) is None

    def test_empty_dataframe_returns_none(self):
        """空 DataFrame → None"""
        with patch("src.data.market_size_fetcher.ak.fund_individual_basic_info_xq",
                    return_value=pd.DataFrame()), \
             patch("src.data.market_size_fetcher.time.sleep"):
            assert fetch_size_xq("000001", delay_s=0) is None

    def test_all_fields_empty_returns_none(self):
        """三个字段都解析失败 → 视为整体失败，返回 None"""
        df = pd.DataFrame({"item": ["基金代码"], "value": ["000001"]})
        with patch("src.data.market_size_fetcher.ak.fund_individual_basic_info_xq",
                    return_value=df), \
             patch("src.data.market_size_fetcher.time.sleep"):
            assert fetch_size_xq("000001", delay_s=0) is None

    def test_general_exception_returns_none(self):
        """任意异常 → None（不抛）"""
        with patch("src.data.market_size_fetcher.ak.fund_individual_basic_info_xq",
                    side_effect=ConnectionError("network error")), \
             patch("src.data.market_size_fetcher.time.sleep"):
            assert fetch_size_xq("000001", delay_s=0) is None


# ── fetch_size fallback 链 ────────────────────────────────


class TestFetchSizeFallback:
    """fetch_size 雪球 → 东财 fallback"""

    def test_xueqiu_succeeds_returns_xueqiu_data(self):
        """雪球成功 → 直接返回雪球结果，不调东财"""
        xq_df = _mock_xueqiu_df(size="39.38亿")
        with patch("src.data.market_size_fetcher.ak.fund_individual_basic_info_xq",
                    return_value=xq_df) as mock_xq, \
             patch("src.data.market_size_fetcher.requests.get") as mock_eastmoney, \
             patch("src.data.market_size_fetcher.time.sleep"):
            result = fetch_size("000001", delay_s_xq=0, delay_s_eastmoney=0)

        assert result["size_yi"] == 39.38
        assert mock_xq.called
        # 东财不应被调用
        assert not mock_eastmoney.called

    def test_xueqiu_key_error_falls_back_to_eastmoney(self):
        """雪球 KeyError 'data' → fallback 东财成功"""
        eastmoney_resp = _mock_response({"ENDNAV": 100000000.0})
        with patch("src.data.market_size_fetcher.ak.fund_individual_basic_info_xq",
                    side_effect=KeyError("data")), \
             patch("src.data.market_size_fetcher.requests.get",
                    return_value=eastmoney_resp), \
             patch("src.data.market_size_fetcher.time.sleep"):
            result = fetch_size("007130", delay_s_xq=0, delay_s_eastmoney=0)

        # fallback 拿到东财结果
        assert result["size_yi"] == 1.0

    def test_xueqiu_exception_falls_back_to_eastmoney(self):
        """雪球通用异常 → fallback 东财"""
        eastmoney_resp = _mock_response({"ENDNAV": 200000000.0})
        with patch("src.data.market_size_fetcher.ak.fund_individual_basic_info_xq",
                    side_effect=ConnectionError("net error")), \
             patch("src.data.market_size_fetcher.requests.get",
                    return_value=eastmoney_resp), \
             patch("src.data.market_size_fetcher.time.sleep"):
            result = fetch_size("007130", delay_s_xq=0, delay_s_eastmoney=0)
        assert result["size_yi"] == 2.0

    def test_both_fail_returns_none(self):
        """雪球 + 东财都失败 → None"""
        with patch("src.data.market_size_fetcher.ak.fund_individual_basic_info_xq",
                    side_effect=KeyError("data")), \
             patch("src.data.market_size_fetcher.requests.get",
                    side_effect=ConnectionError("net error")), \
             patch("src.data.market_size_fetcher.time.sleep"):
            assert fetch_size("007130", delay_s_xq=0, delay_s_eastmoney=0) is None

    def test_xueqiu_all_fields_empty_falls_back(self):
        """雪球三个字段都空 → fallback 东财"""
        # 雪球只返 1 行（基金代码），size/estab/mgr 全空
        xq_df = pd.DataFrame({"item": ["基金代码"], "value": ["000001"]})
        eastmoney_resp = _mock_response({"ENDNAV": 500000000.0})
        with patch("src.data.market_size_fetcher.ak.fund_individual_basic_info_xq",
                    return_value=xq_df), \
             patch("src.data.market_size_fetcher.requests.get",
                    return_value=eastmoney_resp), \
             patch("src.data.market_size_fetcher.time.sleep"):
            result = fetch_size("007130", delay_s_xq=0, delay_s_eastmoney=0)
        assert result["size_yi"] == 5.0


# ── fetch_market_size 批量 ────────────────────────────────


class TestFetchMarketSize:
    """fetch_market_size 批量函数（雪球优先 + fallback）"""

    def test_iterates_all_codes_xueqiu(self):
        """批量调用应按入参顺序逐只拉取（雪球路径）"""
        dfs = [_mock_xueqiu_df(size=f"{i}.0亿") for i in range(3)]
        with patch("src.data.market_size_fetcher.ak.fund_individual_basic_info_xq",
                    side_effect=dfs), \
             patch("src.data.market_size_fetcher.requests.get") as mock_eastmoney, \
             patch("src.data.market_size_fetcher.time.sleep"):
            rows = fetch_market_size(["000001", "000002", "000003"],
                                      delay_s_xq=0, delay_s_eastmoney=0)

        assert len(rows) == 3
        assert [r["code"] for r in rows] == ["000001", "000002", "000003"]
        assert [r["size_yi"] for r in rows] == [0.0, 1.0, 2.0]
        assert not mock_eastmoney.called

    def test_fallback_per_code(self):
        """雪球失败的 code 自动 fallback 东财"""
        xq_results = [
            _mock_xueqiu_df(size="1.0亿"),       # 000001 成功
            KeyError("data"),                    # 000002 失败 → fallback
            _mock_xueqiu_df(size="3.0亿"),       # 000003 成功
        ]
        eastmoney_resp = _mock_response({"ENDNAV": 200000000.0})

        with patch("src.data.market_size_fetcher.ak.fund_individual_basic_info_xq",
                    side_effect=xq_results), \
             patch("src.data.market_size_fetcher.requests.get",
                    return_value=eastmoney_resp), \
             patch("src.data.market_size_fetcher.time.sleep"):
            rows = fetch_market_size(["000001", "000002", "000003"],
                                      delay_s_xq=0, delay_s_eastmoney=0)

        # 三只都成功
        assert len(rows) == 3
        result_by_code = {r["code"]: r["size_yi"] for r in rows}
        assert result_by_code["000001"] == 1.0  # 雪球
        assert result_by_code["000002"] == 2.0  # fallback 东财
        assert result_by_code["000003"] == 3.0  # 雪球

    def test_empty_input_returns_empty_list(self):
        with patch("src.data.market_size_fetcher.time.sleep"):
            rows = fetch_market_size([], delay_s_xq=0, delay_s_eastmoney=0)
        assert rows == []
