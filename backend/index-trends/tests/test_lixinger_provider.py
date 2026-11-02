"""理杏仁供应商适配层测试（脱网）。"""
from __future__ import annotations

import httpx
import pytest

from src.data import lixinger as lx


def _body(*rows: dict) -> dict:
    return {"code": 1, "msg": "", "data": list(rows)}


def _row(date: str = "2026-10-30T15:00:00+08:00", **overrides) -> dict:
    row = {
        "stockCode": "000300",
        "date": date,
        lx.METRIC_PE_TTM: 12.3456,
        lx.METRIC_CVPOS: 0.565952,
    }
    row.update(overrides)
    return row


class _FakeResponse:
    def __init__(self, payload, status_code=200, raises: Exception | None = None):
        self._payload = payload
        self.status_code = status_code
        self._raises = raises

    def json(self):
        if self._raises is not None:
            raise self._raises
        return self._payload


class _FakeClient:
    def __init__(self, response=None, error: Exception | None = None):
        self.response = response
        self.error = error
        self.calls: list[dict] = []

    def post(self, url, json=None):
        self.calls.append({"url": url, "json": json})
        if self.error is not None:
            raise self.error
        return self.response

    def close(self):
        return None


# ---- 解析 ----
def test_parse_returns_qualified_point():
    points = lx.parse_fundamental(_body(_row()), "000300", "2026-10-30")
    assert len(points) == 1
    assert points[0].date == "2026-10-30"
    assert points[0].pe_ttm == pytest.approx(12.3456)
    assert points[0].percentile_ratio == pytest.approx(0.565952)


def test_parse_normalizes_timezone_to_beijing_date():
    # 供应商用 +08:00；跨时区表示也要落到同一个北京时间自然日
    points = lx.parse_fundamental(
        _body(_row(date="2026-10-30T07:00:00+00:00")), "000300", "2026-10-30"
    )
    assert points[0].date == "2026-10-30"


def test_parse_accepts_ratio_bounds():
    zero = lx.parse_fundamental(_body(_row(**{lx.METRIC_CVPOS: 0})), "000300", "2026-10-30")
    one = lx.parse_fundamental(_body(_row(**{lx.METRIC_CVPOS: 1})), "000300", "2026-10-30")
    assert zero[0].percentile_ratio == 0
    assert one[0].percentile_ratio == 1


@pytest.mark.parametrize(
    "overrides",
    [
        {lx.METRIC_PE_TTM: 0},
        {lx.METRIC_PE_TTM: -1},
        {lx.METRIC_PE_TTM: float("nan")},
        {lx.METRIC_PE_TTM: float("inf")},
        {lx.METRIC_PE_TTM: True},
        {lx.METRIC_PE_TTM: "12.3"},
        {lx.METRIC_CVPOS: -0.01},
        {lx.METRIC_CVPOS: 1.01},
        {lx.METRIC_CVPOS: float("nan")},
        {lx.METRIC_CVPOS: False},
        {lx.METRIC_CVPOS: None},
    ],
)
def test_parse_rejects_invalid_values(overrides):
    with pytest.raises(lx.LixingerError) as exc:
        lx.parse_fundamental(_body(_row(**overrides)), "000300", "2026-10-30")
    assert exc.value.reason == "invalid_data"


def test_parse_skips_mismatched_stock_code():
    with pytest.raises(lx.LixingerError):
        lx.parse_fundamental(_body(_row(stockCode="000016")), "000300", "2026-10-30")


def test_parse_rejects_future_record():
    with pytest.raises(lx.LixingerError):
        lx.parse_fundamental(_body(_row(date="2026-11-05T15:00:00+08:00")), "000300", "2026-10-30")


def test_parse_keeps_only_qualified_rows():
    body = _body(_row(), _row(date="2026-10-29T15:00:00+08:00", **{lx.METRIC_PE_TTM: 0}))
    points = lx.parse_fundamental(body, "000300", "2026-10-30")
    assert [p.date for p in points] == ["2026-10-30"]


def test_parse_empty_data_is_not_error():
    assert lx.parse_fundamental({"code": 1, "data": []}, "000300", "2026-10-30") == []


def test_parse_rejects_business_error_code():
    with pytest.raises(lx.LixingerError) as exc:
        lx.parse_fundamental({"code": 4001, "msg": "no permission"}, "000300", "2026-10-30")
    assert exc.value.reason == "upstream_error"
    assert "no permission" not in str(exc.value)   # 不回显供应商正文


def test_parse_rejects_non_json_body():
    with pytest.raises(lx.LixingerError) as exc:
        lx.parse_fundamental("not-a-dict", "000300", "2026-10-30")
    assert exc.value.reason == "invalid_response"


def test_parse_rejects_missing_data_key():
    with pytest.raises(lx.LixingerError) as exc:
        lx.parse_fundamental({"code": 1}, "000300", "2026-10-30")
    assert exc.value.reason == "invalid_response"


# ---- 请求 ----
def test_fetch_sends_explicit_range_and_token():
    client = _FakeClient(_FakeResponse(_body(_row())))
    lx.fetch_fundamental(client, "secret-token", "000300", "2026-10-30")
    payload = client.calls[0]["json"]
    assert payload["stockCodes"] == ["000300"]
    assert payload["metricsList"] == [lx.METRIC_PE_TTM, lx.METRIC_CVPOS]
    assert payload["endDate"] == "2026-10-30"
    assert payload["startDate"] == "2026-09-30"   # 回看 30 个日历日
    assert payload["token"] == "secret-token"


def test_fetch_without_token_does_not_request():
    client = _FakeClient(_FakeResponse(_body(_row())))
    with pytest.raises(lx.LixingerError) as exc:
        lx.fetch_fundamental(client, "", "000300", "2026-10-30")
    assert exc.value.reason == "token_not_configured"
    assert client.calls == []


def test_fetch_maps_network_error_without_token_leak():
    client = _FakeClient(error=httpx.ConnectError("boom"))
    with pytest.raises(lx.LixingerError) as exc:
        lx.fetch_fundamental(client, "secret-token", "000300", "2026-10-30")
    assert exc.value.reason == "network_error"
    assert "secret-token" not in str(exc.value)


def test_fetch_maps_http_error():
    client = _FakeClient(_FakeResponse({}, status_code=401))
    with pytest.raises(lx.LixingerError) as exc:
        lx.fetch_fundamental(client, "secret-token", "000300", "2026-10-30")
    assert exc.value.reason == "http_error"
    assert "secret-token" not in str(exc.value)


def test_fetch_rejects_non_json_response():
    client = _FakeClient(_FakeResponse(None, raises=ValueError("no json")))
    with pytest.raises(lx.LixingerError) as exc:
        lx.fetch_fundamental(client, "secret-token", "000300", "2026-10-30")
    assert exc.value.reason == "invalid_response"


# ---- 选取 ----
def test_latest_qualified_picks_newest_ignoring_order():
    points = [
        lx.ValuationPoint(date="2026-10-28", pe_ttm=1.0, percentile_ratio=0.1),
        lx.ValuationPoint(date="2026-10-30", pe_ttm=2.0, percentile_ratio=0.2),
        lx.ValuationPoint(date="2026-10-29", pe_ttm=3.0, percentile_ratio=0.3),
    ]
    picked = lx.latest_qualified(points, "2026-10-30")
    assert picked is not None and picked.date == "2026-10-30"


def test_latest_qualified_excludes_future():
    points = [lx.ValuationPoint(date="2026-11-02", pe_ttm=1.0, percentile_ratio=0.1)]
    assert lx.latest_qualified(points, "2026-10-30") is None
