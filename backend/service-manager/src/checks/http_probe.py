"""HTTP 可访问性探测（design §6 URL）。

- 先 HEAD，405/501 时退回流式 GET，最多读 64 KiB
- 单次总超时 10 秒，并发上限 4（由调用方持有 semaphore）
- 重定向最多 3 跳，每跳重新校验协议与主机
- 200–399 → reachable；401/403 → auth_required；其余 → unexpected_status
- TLS 握手失败独立报错，不绕过验证当作成功
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import httpx

from src.models import UrlState
from src.urls import is_loopback_host, parse_http_url
from src.checks.common import CheckOutcome, CheckStatus

MAX_REDIRECTS = 3
MAX_BODY_BYTES = 64 * 1024
DEFAULT_TIMEOUT = 10.0
DEFAULT_CONCURRENCY = 4


@dataclass
class ProbeConfig:
    timeout: float = DEFAULT_TIMEOUT
    concurrency: int = DEFAULT_CONCURRENCY
    max_redirects: int = MAX_REDIRECTS


def classify_status(
    status_code: int, expected_ranges: list[str] | None = None
) -> UrlState:
    for item in expected_ranges or []:
        text = item.strip()
        if not text:
            continue
        if "-" in text:
            low_text, high_text = text.split("-", 1)
            try:
                low, high = int(low_text), int(high_text)
            except ValueError:
                continue
            if low <= status_code <= high:
                return UrlState.REACHABLE
        else:
            try:
                if int(text) == status_code:
                    return UrlState.REACHABLE
            except ValueError:
                continue
    if 200 <= status_code <= 399:
        return UrlState.REACHABLE
    if status_code in (401, 403):
        return UrlState.AUTH_REQUIRED
    return UrlState.UNEXPECTED_STATUS


@dataclass
class ProbeResult:
    state: UrlState
    status_code: int | None = None
    method: str = ""
    final_url: str = ""
    redirects: int = 0
    error_code: str | None = None
    error_message: str | None = None
    body_bytes: int = 0
    truncated: bool = False


async def probe_url(
    url: str,
    *,
    expected_ranges: list[str] | None = None,
    config: ProbeConfig | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> ProbeResult:
    cfg = config or ProbeConfig()
    parsed = parse_http_url(url)
    if is_loopback_host(parsed.host):
        return ProbeResult(
            state=UrlState.UNKNOWN,
            error_code="loopback_target",
            error_message=(
                "探测目标不能是 localhost：容器内 localhost 指管理台自身"
            ),
        )
    redirects = 0
    current = url
    method = "HEAD"
    async with httpx.AsyncClient(
        follow_redirects=False,
        timeout=httpx.Timeout(cfg.timeout),
        transport=transport,
        verify=True,
    ) as client:
        while True:
            try:
                if method == "HEAD":
                    response = await client.head(current)
                else:
                    async with client.stream("GET", current) as stream:
                        # 只读最多 64 KiB：单个 chunk 可能远大于上限，因此
                        # 计数按实际上限截断并标 truncated（不断言读完了整个响应）。
                        body = 0
                        truncated = False
                        async for chunk in stream.aiter_bytes():
                            body += len(chunk)
                            if body >= MAX_BODY_BYTES:
                                truncated = True
                                break
                        return _result_from_status(
                            stream.status_code,
                            expected_ranges,
                            method="GET",
                            final_url=str(stream.url),
                            redirects=redirects,
                            body_bytes=min(body, MAX_BODY_BYTES),
                            truncated=truncated,
                        )
            except httpx.TooManyRedirects:
                return ProbeResult(
                    state=UrlState.UNREACHABLE,
                    error_code="too_many_redirects",
                    error_message="重定向次数过多",
                    redirects=redirects,
                )
            except httpx.TimeoutException:
                return ProbeResult(
                    state=UrlState.UNREACHABLE,
                    method=method,
                    error_code="timeout",
                    error_message="请求超时",
                    redirects=redirects,
                )
            except httpx.ConnectError as exc:
                return ProbeResult(
                    state=UrlState.UNREACHABLE,
                    method=method,
                    error_code="connect_error",
                    error_message=str(exc) or "无法连接",
                    redirects=redirects,
                )
            except httpx.HTTPError as exc:
                return ProbeResult(
                    state=UrlState.UNREACHABLE,
                    method=method,
                    error_code="http_error",
                    error_message=str(exc) or "请求失败",
                    redirects=redirects,
                )

            if response.status_code in (301, 302, 303, 307, 308):
                location = response.headers.get("location", "")
                if not location:
                    return _result_from_status(
                        response.status_code,
                        expected_ranges,
                        method=method,
                        final_url=str(response.url),
                        redirects=redirects,
                        body_bytes=0,
                    )
                redirects += 1
                if redirects > cfg.max_redirects:
                    return ProbeResult(
                        state=UrlState.UNREACHABLE,
                        status_code=response.status_code,
                        method=method,
                        error_code="too_many_redirects",
                        error_message=f"重定向超过 {cfg.max_redirects} 跳",
                        redirects=redirects,
                    )
                try:
                    next_url = str(response.url.join(location))
                    next_parsed = parse_http_url(next_url)
                except Exception as exc:  # noqa: BLE001 - 非法重定向目标
                    return ProbeResult(
                        state=UrlState.UNREACHABLE,
                        status_code=response.status_code,
                        method=method,
                        error_code="invalid_redirect",
                        error_message=f"重定向目标不合法: {exc}",
                        redirects=redirects,
                    )
                if is_loopback_host(next_parsed.host):
                    return ProbeResult(
                        state=UrlState.UNREACHABLE,
                        status_code=response.status_code,
                        method=method,
                        error_code="loopback_target",
                        error_message="重定向到 localhost，已拒绝",
                        redirects=redirects,
                    )
                current = next_url
                continue

            if response.status_code in (405, 501) and method == "HEAD":
                method = "GET"
                continue

            return _result_from_status(
                response.status_code,
                expected_ranges,
                method=method,
                final_url=str(response.url),
                redirects=redirects,
                body_bytes=0,
            )


def _result_from_status(
    status_code: int,
    expected_ranges: list[str] | None,
    *,
    method: str,
    final_url: str,
    redirects: int,
    body_bytes: int,
    truncated: bool = False,
) -> ProbeResult:
    return ProbeResult(
        state=classify_status(status_code, expected_ranges),
        status_code=status_code,
        method=method,
        final_url=final_url,
        redirects=redirects,
        body_bytes=body_bytes,
        truncated=truncated,
    )


def to_outcome(result: ProbeResult) -> CheckOutcome:
    """网络/协议层的失败 → check_status=error（旧结果保留标 stale）。

    HTTP 状态码与证书异常都是「完成检查得到的观测」，走 success。
    """
    payload: dict[str, Any] = {
        "state": result.state.value,
        "status_code": result.status_code,
        "method": result.method,
        "final_url": result.final_url,
        "redirects": result.redirects,
        "body_bytes": result.body_bytes,
        "body_truncated": result.truncated,
        "perspective": "probed from service-manager backend",
    }
    if result.error_code:
        return CheckOutcome(
            check_status=CheckStatus.ERROR,
            current_state=result.state.value,
            payload=payload,
            error_code=result.error_code,
            error_message=result.error_message,
        )
    return CheckOutcome(
        check_status=CheckStatus.SUCCESS,
        current_state=result.state.value,
        payload=payload,
    )


async def probe_many(
    targets: list[tuple[str, list[str] | None]],
    *,
    config: ProbeConfig | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> list[ProbeResult]:
    cfg = config or ProbeConfig()
    semaphore = asyncio.Semaphore(max(1, cfg.concurrency))

    async def _one(url: str, ranges: list[str] | None) -> ProbeResult:
        async with semaphore:
            return await probe_url(
                url, expected_ranges=ranges, config=cfg, transport=transport
            )

    return await asyncio.gather(
        *[_one(url, ranges) for url, ranges in targets], return_exceptions=False
    )
