"""
market_size_fetcher 单测（mock requests.get + time.sleep，不联网）

关键回归点：
- ENDNAV 单位换算：ENDNAV（单位元）÷1e8 = 亿元
- ESTABDATE 解析为 date
- JJGS 空字符串 → None（非空字符串保留）
- Datas 为空 → 返回 None
- requests.get 抛异常 → 返回 None（不抛）
- fetch_market_size 顺序遍历 + 失败跳过
"""
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from src.data.market_size_fetcher import fetch_size, fetch_market_size


def _mock_response(datas: dict | None, status_code: int = 200) -> MagicMock:
    """构造 requests.get 的 mock 响应"""
    r = MagicMock()
    r.status_code = status_code
    r.raise_for_status = MagicMock()
    r.json.return_value = {"Datas": datas} if datas is not None else {}
    return r


class TestFetchSize:
    """fetch_size 单只函数"""

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
            result = fetch_size("007130", delay_s=0)

        assert result is not None
        assert result["code"] == "007130"
        assert result["established_date"] == date(2019, 4, 3)
        # 342743333.13 / 1e8 ≈ 3.4274
        assert result["size_yi"] == pytest.approx(3.4274, abs=1e-4)
        # age_years：基于 today 计算（today=2026-09-09，差 7 年多）
        assert result["age_years"] is not None
        assert 7.0 < result["age_years"] < 7.5
        assert result["mgr_company"] == "中庚基金"

    def test_endnav_unit_division_by_1e8(self):
        """单位换算边界：ENDNAV=1e8 应得 1.0 亿元；ENDNAV=0.5e8 应得 0.5 亿元。"""
        # 1e8 元 = 1 亿元
        r1 = _mock_response({"ENDNAV": 100000000.0})
        with patch("src.data.market_size_fetcher.requests.get", return_value=r1), \
             patch("src.data.market_size_fetcher.time.sleep"):
            result = fetch_size("000001", delay_s=0)
        assert result["size_yi"] == 1.0

        # 5.5e8 元 = 5.5 亿元
        r2 = _mock_response({"ENDNAV": 550000000.0})
        with patch("src.data.market_size_fetcher.requests.get", return_value=r2), \
             patch("src.data.market_size_fetcher.time.sleep"):
            result = fetch_size("000002", delay_s=0)
        assert result["size_yi"] == 5.5

    def test_endnav_none_leaves_size_none(self):
        """ENDNAV=None → size_yi=None（不抛）"""
        mock_resp = _mock_response({"ESTABDATE": "2020-01-01", "ENDNAV": None, "JJGS": "X"})
        with patch("src.data.market_size_fetcher.requests.get", return_value=mock_resp), \
             patch("src.data.market_size_fetcher.time.sleep"):
            result = fetch_size("000001", delay_s=0)
        assert result["size_yi"] is None
        assert result["established_date"] == date(2020, 1, 1)
        assert result["mgr_company"] == "X"

    def test_endnav_invalid_string_leaves_size_none(self):
        """ENDNAV 非数字字符串 → size_yi=None（不抛）"""
        mock_resp = _mock_response({"ENDNAV": "abc"})
        with patch("src.data.market_size_fetcher.requests.get", return_value=mock_resp), \
             patch("src.data.market_size_fetcher.time.sleep"):
            result = fetch_size("000001", delay_s=0)
        assert result["size_yi"] is None

    def test_jjgs_empty_string_becomes_none(self):
        """JJGS 空字符串 → mgr_company=None（避免空串顶掉已有公司名）"""
        mock_resp = _mock_response({"JJGS": ""})
        with patch("src.data.market_size_fetcher.requests.get", return_value=mock_resp), \
             patch("src.data.market_size_fetcher.time.sleep"):
            result = fetch_size("000001", delay_s=0)
        assert result["mgr_company"] is None

    def test_jjgs_whitespace_only_becomes_none(self):
        """JJGS 空白字符串 → mgr_company=None"""
        mock_resp = _mock_response({"JJGS": "   "})
        with patch("src.data.market_size_fetcher.requests.get", return_value=mock_resp), \
             patch("src.data.market_size_fetcher.time.sleep"):
            result = fetch_size("000001", delay_s=0)
        assert result["mgr_company"] is None

    def test_estabdate_missing_leaves_date_none(self):
        """ESTABDATE 缺失 → established_date=None / age_years=None"""
        mock_resp = _mock_response({"ENDNAV": 100.0, "JJGS": "X"})
        with patch("src.data.market_size_fetcher.requests.get", return_value=mock_resp), \
             patch("src.data.market_size_fetcher.time.sleep"):
            result = fetch_size("000001", delay_s=0)
        assert result["established_date"] is None
        assert result["age_years"] is None
        assert result["size_yi"] == 0.0  # 100 / 1e8 = 1e-6，round(4) 后为 0.0

    def test_estabdate_short_string_ignored(self):
        """ESTABDATE 长度 < 10 → 跳过解析"""
        mock_resp = _mock_response({"ESTABDATE": "2019", "ENDNAV": 100.0})
        with patch("src.data.market_size_fetcher.requests.get", return_value=mock_resp), \
             patch("src.data.market_size_fetcher.time.sleep"):
            result = fetch_size("000001", delay_s=0)
        assert result["established_date"] is None
        assert result["age_years"] is None

    def test_estabdate_iso_with_extra_suffix(self):
        """ESTABDATE='2019-04-03T00:00:00' → 截前 10 位仍得 '2019-04-03'"""
        mock_resp = _mock_response({"ESTABDATE": "2019-04-03T00:00:00"})
        with patch("src.data.market_size_fetcher.requests.get", return_value=mock_resp), \
             patch("src.data.market_size_fetcher.time.sleep"):
            result = fetch_size("000001", delay_s=0)
        assert result["established_date"] == date(2019, 4, 3)

    def test_datas_empty_returns_none(self):
        """Datas 为空 dict → 返回 None（不算成功）"""
        mock_resp = _mock_response({})
        with patch("src.data.market_size_fetcher.requests.get", return_value=mock_resp), \
             patch("src.data.market_size_fetcher.time.sleep"):
            result = fetch_size("000001", delay_s=0)
        assert result is None

    def test_datas_key_missing_returns_none(self):
        """响应 JSON 无 Datas key → 返回 None"""
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"foo": "bar"}
        with patch("src.data.market_size_fetcher.requests.get", return_value=mock_resp), \
             patch("src.data.market_size_fetcher.time.sleep"):
            result = fetch_size("000001", delay_s=0)
        assert result is None

    def test_requests_exception_returns_none(self):
        """requests.get 抛异常 → 返回 None（不抛）"""
        with patch("src.data.market_size_fetcher.requests.get",
                    side_effect=ConnectionError("network error")), \
             patch("src.data.market_size_fetcher.time.sleep"):
            result = fetch_size("000001", delay_s=0)
        assert result is None

    def test_http_status_error_returns_none(self):
        """HTTP 4xx/5xx → 返回 None"""
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = RuntimeError("404 Not Found")
        with patch("src.data.market_size_fetcher.requests.get", return_value=mock_resp), \
             patch("src.data.market_size_fetcher.time.sleep"):
            result = fetch_size("000001", delay_s=0)
        assert result is None

    def test_invalid_json_returns_none(self):
        """r.json() 抛 ValueError → 返回 None"""
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.side_effect = ValueError("invalid json")
        with patch("src.data.market_size_fetcher.requests.get", return_value=mock_resp), \
             patch("src.data.market_size_fetcher.time.sleep"):
            result = fetch_size("000001", delay_s=0)
        assert result is None

    def test_url_contains_code_and_platform_params(self):
        """URL 必须含 FCODE / deviceid / plat 参数（否则接口拒绝）"""
        mock_resp = _mock_response({"ENDNAV": 1.0})
        with patch("src.data.market_size_fetcher.requests.get", return_value=mock_resp) as mock_get, \
             patch("src.data.market_size_fetcher.time.sleep"):
            fetch_size("007130", delay_s=0)
            called_url = mock_get.call_args[0][0]
            assert "FCODE=007130" in called_url
            assert "deviceid=W" in called_url
            assert "plat=Wap" in called_url
            assert "product=EFund" in called_url

    def test_user_agent_and_referer_headers_sent(self):
        """Headers 含 User-Agent / Referer（否则东财会拒绝）

        UA 用 iOS Safari（移动端 UA），Chrome UA 实测触发「网络繁忙」限频。
        """
        mock_resp = _mock_response({"ENDNAV": 1.0})
        with patch("src.data.market_size_fetcher.requests.get", return_value=mock_resp) as mock_get, \
             patch("src.data.market_size_fetcher.time.sleep"):
            fetch_size("000001", delay_s=0)
            headers = mock_get.call_args.kwargs["headers"]
            ua = headers["User-Agent"]
            assert "iPhone" in ua, f"UA 必须是移动端（实测 Chrome UA 触发限频），实际: {ua}"
            assert headers["Referer"] == "https://fund.eastmoney.com/"

    def test_sleep_called_with_delay(self):
        """delay_s > 0 时 time.sleep 会被调（防东财限频）"""
        mock_resp = _mock_response({"ENDNAV": 1.0})
        with patch("src.data.market_size_fetcher.requests.get", return_value=mock_resp), \
             patch("src.data.market_size_fetcher.time.sleep") as mock_sleep:
            fetch_size("000001", delay_s=0.4)
            mock_sleep.assert_called_once_with(0.4)


class TestFetchMarketSize:
    """fetch_market_size 批量函数"""

    def test_iterates_all_codes_in_order(self):
        """批量调用应按入参顺序逐只拉取"""
        mock_responses = [
            _mock_response({"ENDNAV": 100.0, "JJGS": f"公司{i}"})
            for i in range(3)
        ]
        with patch("src.data.market_size_fetcher.requests.get",
                    side_effect=mock_responses), \
             patch("src.data.market_size_fetcher.time.sleep"):
            rows = fetch_market_size(["000001", "000002", "000003"], delay_s=0)

        assert len(rows) == 3
        assert [r["code"] for r in rows] == ["000001", "000002", "000003"]
        assert [r["mgr_company"] for r in rows] == ["公司0", "公司1", "公司2"]

    def test_skips_failed_codes(self):
        """单只失败（requests 抛错）不中断批量，跳过该 code"""
        mock_resp_ok = _mock_response({"ENDNAV": 100.0, "JJGS": "X"})

        def side_effect(url, **kw):
            if "000002" in url:
                raise ConnectionError("boom")
            return mock_resp_ok

        with patch("src.data.market_size_fetcher.requests.get",
                    side_effect=side_effect), \
             patch("src.data.market_size_fetcher.time.sleep"):
            rows = fetch_market_size(["000001", "000002", "000003"], delay_s=0)

        # 失败那只被跳过，其他两只成功
        assert len(rows) == 2
        assert {r["code"] for r in rows} == {"000001", "000003"}

    def test_empty_input_returns_empty_list(self):
        with patch("src.data.market_size_fetcher.time.sleep"):
            rows = fetch_market_size([], delay_s=0)
        assert rows == []
