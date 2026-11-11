"""manager_profile_fetcher 单测：mock HTTP，不联网。

验证 contract：
- 经理表解析保留经理 ID（akshare 封装丢弃的列）
- 档案页历任表解析（含已离任、天数解析）
- BOM/编码陷阱：内容按 utf-8 解码
- 复权序列：equityReturn 连乘，首点 1.0
"""
from unittest.mock import patch

import pytest

from src.data.manager_profile_fetcher import (
    fetch_adjusted_series,
    fetch_manager_table_with_id,
    fetch_manager_tenures,
    parse_tenure_days,
)


class FakeResp:
    def __init__(self, content: bytes, text: str | None = None):
        self.content = content
        self._text = text
        self.status_code = 200

    @property
    def text(self):
        return self._text if self._text is not None else self.content.decode("utf-8", "replace")

    def raise_for_status(self):
        pass


# ── 经理表 ────────────────────────────────────────────

def _mk_dt14_row(mid, name, company, codes, days, best, scale):
    return [mid, name, "", company, ",".join(codes), "n,".join(codes),
            str(days), f"{best}%", codes[0] if codes else "", "", f"{scale}亿元", f"{best}%"]


class TestManagerTableWithId:
    def test_keeps_manager_id(self):
        """核心回归：akshare 封装丢弃经理 ID，本函数必须保留（重名防串号的根基）。"""
        payload = {"data": [
            _mk_dt14_row("30189744", "张坤", "易方达基金", ["110011", "005827"], 5191, 311.31, 293.07),
            _mk_dt14_row("30011111", "陈涵", "工银瑞信基金", ["000001"], 2700, 50.0, 100.0),
            _mk_dt14_row("30022222", "陈涵", "华夏基金", ["000002"], 580, 10.0, 0.5),
        ], "pages": 1, "record": 3}

        with patch("src.data.manager_profile_fetcher._get_with_retry",
                   return_value=FakeResp(b"", text=f"var returnjson= {payload}")):
            rows = fetch_manager_table_with_id()

        assert len(rows) == 3
        by_id = {r["manager_id"]: r for r in rows}
        # 重名经理落在不同主键行
        assert by_id["30011111"]["name"] == "陈涵"
        assert by_id["30022222"]["name"] == "陈涵"
        assert by_id["30011111"]["company"] != by_id["30022222"]["company"]
        assert by_id["30189744"]["career_days"] == 5191
        assert by_id["30189744"]["fund_codes"] == ["110011", "005827"]
        assert by_id["30189744"]["current_scale_yi"] == 293.07

    def test_paginates_all_pages(self):
        p1 = {"data": [_mk_dt14_row("1", "a", "c", ["000001"], 100, 1.0, 1.0)], "pages": 2}
        p2 = {"data": [_mk_dt14_row("2", "b", "c", ["000002"], 200, 2.0, 2.0)], "pages": 2}
        resp = [FakeResp(b"", text=f"var returnjson= {p1}"), FakeResp(b"", text=f"var returnjson= {p2}")]

        with patch("src.data.manager_profile_fetcher._get_with_retry", side_effect=resp):
            rows = fetch_manager_table_with_id()
        assert len(rows) == 2

    def test_bad_rows_skipped(self):
        payload = {"data": [[], ["only", "two"], _mk_dt14_row("9", "ok", "c", ["000009"], 10, 1, 1)],
                   "pages": 1}
        with patch("src.data.manager_profile_fetcher._get_with_retry",
                   return_value=FakeResp(b"", text=f"var returnjson= {payload}")):
            rows = fetch_manager_table_with_id()
        assert [r["manager_id"] for r in rows] == ["9"]


# ── 档案页 ────────────────────────────────────────────

def _mk_profile_html(rows: list[list[str]]) -> bytes:
    """构造档案页 HTML：body 后第 2 个 table 是历任表。"""
    trs = "".join(
        "<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>" for row in rows
    )
    return (
        "<html><body>"
        "<table><tr><td>nav</td></tr></table>"
        f"<table><tr><th>基金代码</th><th>基金名称</th><th>链接</th><th>类型</th>"
        f"<th>规模</th><th>任职时间</th><th>任职天数</th><th>任职回报</th></tr>{trs}</table>"
        "</body></html>"
    ).encode("utf-8-sig")  # 带 BOM，模拟真实响应


class TestManagerTenures:
    FIXTURE = [
        ["110011", "易方达优质精选混合(QDII)", "链接", "QDII-混合", "66.84",
         "2012-09-28 ~ 至今", "14年又46天", "311.31%"],
        ["005827", "易方达蓝筹精选混合", "链接", "混合型-偏股", "189.33",
         "2018-09-05 ~ 至今", "8年又68天", "39.93%"],
        ["001373", "易方达新丝路灵活配置混合", "链接", "混合型-灵活", "27.65",
         "2015-11-07 ~ 2021-02-11", "5年又98天", "156.18%"],
    ]

    def test_parse_tenures_with_departed(self):
        """含已离任记录；天数按「X年又Y天」解析。"""
        html = _mk_profile_html(self.FIXTURE)
        with patch("src.data.manager_profile_fetcher._get_with_retry",
                   return_value=FakeResp(html)):
            tenures = fetch_manager_tenures("30189744")

        assert len(tenures) == 3
        by_code = {t["fund_code"]: t for t in tenures}
        assert by_code["110011"]["is_current"] is True
        assert by_code["110011"]["end_date"] is None
        assert by_code["110011"]["tenure_days"] == 14 * 365 + 46
        # 已离任
        assert by_code["001373"]["is_current"] is False
        assert by_code["001373"]["end_date"] == "2021-02-11"
        assert by_code["001373"]["tenure_return_pct"] == pytest.approx(156.18)
        assert by_code["005827"]["fund_type"] == "混合型-偏股"
        assert by_code["005827"]["size_yi"] == pytest.approx(189.33)

    def test_bom_not_corrupting_days(self):
        """编码回归：BOM 响应下「年/天」必须正常解析（requests.text 陷阱）。

        若实现误用 resp.text（ISO-8859-1 解码），中文变乱码 → tenure_days=None。
        """
        html = _mk_profile_html(self.FIXTURE)  # utf-8-sig 带 BOM
        with patch("src.data.manager_profile_fetcher._get_with_retry",
                   return_value=FakeResp(html)):
            tenures = fetch_manager_tenures("x")
        assert all(t["tenure_days"] and t["tenure_days"] > 0 for t in tenures)

    def test_only_tenure_days_no_years(self):
        html = _mk_profile_html([["028160", "广发稳致混合C", "链接", "混合型-偏债", "1.82",
                                  "2026-08-20 ~ 至今", "82天", "0.28%"]])
        with patch("src.data.manager_profile_fetcher._get_with_retry",
                   return_value=FakeResp(html)):
            tenures = fetch_manager_tenures("x")
        assert tenures[0]["tenure_days"] == 82

    def test_empty_page_returns_empty(self):
        html = _mk_profile_html([])
        with patch("src.data.manager_profile_fetcher._get_with_retry",
                   return_value=FakeResp(html)):
            assert fetch_manager_tenures("x") == []


# ── 复权序列 ──────────────────────────────────────────

class TestAdjustedSeries:
    def _mk_pingzhong(self, points: list[dict]) -> bytes:
        import json
        return f"var Data_netWorthTrend = {json.dumps(points)};".encode("utf-8")

    def test_equityReturn_compound(self):
        """复权曲线 = equityReturn 连乘，首点 1.0。"""
        points = [
            {"x": 1132070400000, "y": 1.0, "equityReturn": 0},
            {"x": 1132156800000, "y": 1.05, "equityReturn": 5.0},
            {"x": 1132243200000, "y": 0.9975, "equityReturn": -5.0},
        ]
        with patch("src.data.manager_profile_fetcher._get_with_retry",
                   return_value=FakeResp(self._mk_pingzhong(points))):
            series = fetch_adjusted_series("161005")

        assert series[0][1] == pytest.approx(1.0)
        assert series[1][1] == pytest.approx(1.05)
        assert series[2][1] == pytest.approx(1.05 * 0.95)
        # 日期轴来自毫秒时间戳（北京时间）
        assert series[0][0] == "2005-11-16"

    def test_missing_var_raises(self):
        with patch("src.data.manager_profile_fetcher._get_with_retry",
                   return_value=FakeResp(b"var something_else = [];")):
            with pytest.raises(ValueError, match="Data_netWorthTrend"):
                fetch_adjusted_series("161005")


# ── 天数解析 ──────────────────────────────────────────

class TestParseTenureDays:
    @pytest.mark.parametrize("text,expected", [
        ("14年又46天", 14 * 365 + 46),
        ("82天", 82),
        ("1年又48天", 365 + 48),
        ("3年", 365 * 3),
        ("", None),
        ("- ", None),
        ("无天数", None),
    ])
    def test_parse(self, text, expected):
        assert parse_tenure_days(text) == expected
