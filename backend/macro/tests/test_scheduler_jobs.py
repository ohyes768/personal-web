"""scheduler run_group 组执行器单元测试

mock httpx.AsyncClient 与 is_trading_day，验证：
- 聚合逻辑：全成功 → success / 部分失败 → partial / 全失败 → failed
- 单源失败不中断：失败源后续的 targets 仍被顺序执行
- macro update 端点契约：HTTP 200 + body{success, message, data?}，
  按 body.success 判定成败（success=False 亦为 failed）
- 非交易日 check_trading_day → skipped 且不发任何请求
- self-call URL 拼接：http://127.0.0.1:{port}/api{path}
"""
from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import patch

import pytest

from src.scheduler.jobs import run_group

PORT = 18094  # 任意测试端口：self-call 已被 mock，不会真正发起请求


# ============================================================
# 测试替身
# ============================================================

class FakeCtx:
    """SchedulerManager 最小替身：run_group 只用 jobs_meta 和 port"""

    def __init__(self, jobs_meta: dict[str, dict], port: int = PORT):
        self.jobs_meta = jobs_meta
        self.port = port


class FakeResponse:
    """httpx.Response 替身：status_code / json() / text"""

    def __init__(self, status_code: int = 200, json_body: dict | None = None, text: str = ""):
        self.status_code = status_code
        self._json = json_body if json_body is not None else {}
        self.text = text

    def json(self) -> dict:
        return self._json


class FakeAsyncClient:
    """httpx.AsyncClient 替身：按 URL 返回预设响应或抛异常，记录调用顺序"""

    def __init__(self, by_url: dict[str, Any]):
        self._by_url = by_url
        self.calls: list[str] = []

    async def __aenter__(self) -> "FakeAsyncClient":
        return self

    async def __aexit__(self, *args: Any) -> bool:
        return False

    async def post(self, url: str) -> FakeResponse:
        self.calls.append(url)
        preset = self._by_url[url]
        if isinstance(preset, Exception):
            raise preset
        return preset


def ok_resp(data: Any = None) -> FakeResponse:
    """200 + success=True（macro update 端点成功形态）"""
    return FakeResponse(200, {"success": True, "message": "更新成功", "data": data})


def biz_fail_resp(message: str = "数据更新正在进行中") -> FakeResponse:
    """200 + success=False（macro update 端点业务失败形态，无 409）"""
    return FakeResponse(200, {"success": False, "message": message})


def run_with_mocks(
    spec: dict, by_url: dict[str, Any], *, trading_day: bool = True
) -> tuple[dict, FakeAsyncClient]:
    """mock httpx + is_trading_day 后执行 run_group，返回 (result, client)"""
    ctx = FakeCtx({"test_job": spec})
    client = FakeAsyncClient(by_url)
    with patch("src.scheduler.jobs.httpx.AsyncClient", return_value=client), \
         patch("src.scheduler.jobs.is_trading_day", return_value=trading_day):
        result = asyncio.run(run_group(ctx, "test_job"))
    return result, client


def spec(targets: list[str], check_trading_day: bool = False) -> dict:
    return {
        "id": "test_job",
        "target": "run_group",
        "cron": "0 16 * * 1-5",
        "check_trading_day": check_trading_day,
        "targets": targets,
    }


# ============================================================
# 聚合逻辑：success / partial / failed
# ============================================================

@pytest.mark.unit
def test_all_success_aggregates_to_success():
    """全 success → status=success，count=成功数"""
    s = spec(["/update/vix", "/update/tga"])
    result, _ = run_with_mocks(s, {
        f"http://127.0.0.1:{PORT}/api/update/vix": ok_resp(),
        f"http://127.0.0.1:{PORT}/api/update/tga": ok_resp(),
    })
    assert result["status"] == "success"
    assert result["count"] == 2
    assert len(result["items"]) == 2
    assert all(it["status"] == "success" for it in result["items"])
    assert result["start"] and result["end"]


@pytest.mark.unit
def test_partial_failure_aggregates_to_partial():
    """部分失败 → status=partial，count=成功数，失败 item 记业务 message"""
    s = spec(["/update/vix", "/update/tga", "/update/hibor"])
    result, _ = run_with_mocks(s, {
        f"http://127.0.0.1:{PORT}/api/update/vix": ok_resp(),
        f"http://127.0.0.1:{PORT}/api/update/tga": biz_fail_resp("FRED 拉取失败"),
        f"http://127.0.0.1:{PORT}/api/update/hibor": ok_resp(),
    })
    assert result["status"] == "partial"
    assert result["count"] == 2
    failed = result["items"][1]
    assert failed["path"] == "/update/tga"
    assert failed["status"] == "failed"
    assert failed["error"] == "FRED 拉取失败"


@pytest.mark.unit
def test_all_failed_aggregates_to_failed():
    """全失败（业务失败 + HTTP 500 混合）→ status=failed，count=0"""
    s = spec(["/update/vix", "/update/tga"])
    result, _ = run_with_mocks(s, {
        f"http://127.0.0.1:{PORT}/api/update/vix": biz_fail_resp("上游超时"),
        f"http://127.0.0.1:{PORT}/api/update/tga": FakeResponse(500, text="boom"),
    })
    assert result["status"] == "failed"
    assert result["count"] == 0
    # HTTP 500 的 error 落 HTTP 状态码前缀
    assert result["items"][1]["error"].startswith("HTTP 500")


@pytest.mark.unit
def test_single_failure_does_not_block_rest():
    """单源失败（含网络异常）不中断：后续数据源仍被顺序执行"""
    s = spec(["/update/vix", "/update/tga", "/update/hibor"])
    result, client = run_with_mocks(s, {
        f"http://127.0.0.1:{PORT}/api/update/vix": RuntimeError("connect timeout"),
        f"http://127.0.0.1:{PORT}/api/update/tga": ok_resp(),
        f"http://127.0.0.1:{PORT}/api/update/hibor": ok_resp(),
    })
    # 三个请求全部发出，顺序保序
    assert client.calls == [
        f"http://127.0.0.1:{PORT}/api/update/vix",
        f"http://127.0.0.1:{PORT}/api/update/tga",
        f"http://127.0.0.1:{PORT}/api/update/hibor",
    ]
    assert result["status"] == "partial"
    assert result["count"] == 2
    # 网络异常 item 记 httpx error 前缀
    assert result["items"][0]["status"] == "failed"
    assert result["items"][0]["error"].startswith("httpx error:")


@pytest.mark.unit
def test_self_call_url_shape():
    """self-call URL = http://127.0.0.1:{port}/api{path}（跨层契约）"""
    s = spec(["/update/china-bonds"])
    _, client = run_with_mocks(s, {
        f"http://127.0.0.1:{PORT}/api/update/china-bonds": ok_resp(),
    })
    assert client.calls == [f"http://127.0.0.1:{PORT}/api/update/china-bonds"]


# ============================================================
# 交易日判定
# ============================================================

@pytest.mark.unit
def test_skipped_on_non_trading_day():
    """check_trading_day + 非交易日 → skipped，且不发任何请求"""
    s = spec(["/update/vix", "/update/tga"], check_trading_day=True)
    result, client = run_with_mocks(s, {}, trading_day=False)
    assert result["status"] == "skipped"
    assert result["reason"] == "non_trading_day"
    assert "items" not in result  # 未发请求，无子明细
    assert client.calls == []


@pytest.mark.unit
def test_no_trading_check_when_disabled():
    """check_trading_day=False（全球组）→ 非交易日也照常执行"""
    s = spec(["/update/us-treasuries"], check_trading_day=False)
    result, client = run_with_mocks(s, {
        f"http://127.0.0.1:{PORT}/api/update/us-treasuries": ok_resp(),
    }, trading_day=False)
    assert result["status"] == "success"
    assert len(client.calls) == 1


# ============================================================
# item 字段
# ============================================================

@pytest.mark.unit
def test_item_count_from_list_data_only():
    """count 仅在 data 为列表时取条数；嵌套结构 data 取不到时为 None"""
    s = spec(["/update/fund-flow", "/update/volume"])
    result, _ = run_with_mocks(s, {
        # fund-flow data 为列表 → count=2
        f"http://127.0.0.1:{PORT}/api/update/fund-flow": ok_resp([{"date": "2026-08-26"}, {"date": "2026-08-25"}]),
        # volume data 为嵌套 dict → count=None
        f"http://127.0.0.1:{PORT}/api/update/volume": ok_resp({"volume": {"date": "2026-08-26", "value": 12000.0}}),
    })
    assert result["items"][0]["count"] == 2
    assert result["items"][1]["count"] is None
    assert all("ms" in it for it in result["items"])


@pytest.mark.unit
def test_empty_targets_fails_loud():
    """targets 为空（配置错误）→ failed 且 error 说明"""
    s = spec([])
    result, client = run_with_mocks(s, {})
    assert result["status"] == "failed"
    assert "targets" in result["error"]
    assert client.calls == []
