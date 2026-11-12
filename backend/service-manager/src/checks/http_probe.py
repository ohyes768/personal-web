"""HTTP 可访问性探测（design §6 URL）。

- 先 HEAD，405/501 时退回流式 GET，最多读 64 KiB
- 单次总超时 10 秒，并发上限 4（由调用方持有 semaphore）
- 重定向最多 3 跳，每跳重新校验协议与主机
- 200–399 → reachable；401/403 → auth_required；其余 → unexpected_status
- 证书不被信任（自签/链不全/域名不符）时，先跳过校验重试一次：
  HTTP 层确实答话就算「可达」，证书本身的问题一律交给 TLS 维度说，
  免得把「锁不配钥匙」误报成「门都没开」
"""

from __future__ import annotations

import asyncio
import ssl
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

# 证书校验失败的特征串：httpx 把 ssl 异常包成 ConnectError，原始异常类型
# 不一定还在链上（httpcore 会用文字重塑异常），所以类型 + 文字双判定。
_CERT_ERROR_MARKERS = (
    "certificate_verify_failed",
    "certificate verify failed",
    "self-signed certificate",
    "certificate has expired",
    "hostname mismatch",
    "unable to get local issuer certificate",
)


def is_cert_verification_error(exc: BaseException | None) -> bool:
    """判断异常是不是「证书不被信任」造成的（而不是网络不通）。"""
    current: BaseException | None = exc
    seen = 0
    while current is not None and seen < 5:
        if isinstance(current, ssl.SSLCertVerificationError):
            return True
        text = str(current).lower()
        if any(marker in text for marker in _CERT_ERROR_MARKERS):
            return True
        current = current.__cause__ or current.__context__
        seen += 1
    return False


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
    # 证书校验是否通过。为 False 时表示「跳过校验重试后才拿到响应」，
    # 证书本身的问题由 TLS 维度单独报，这里只留个底。
    tls_verified: bool = True
    tls_error: str | None = None


async def probe_url(
    url: str,
    *,
    expected_ranges: list[str] | None = None,
    config: ProbeConfig | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
    verify: bool = True,
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
        verify=verify,
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
                if verify and is_cert_verification_error(exc):
                    return await _probe_without_cert_check(
                        url,
                        expected_ranges=expected_ranges,
                        cfg=cfg,
                        transport=transport,
                        cert_error=str(exc) or "证书校验失败",
                    )
                return ProbeResult(
                    state=UrlState.UNREACHABLE,
                    method=method,
                    error_code="connect_error",
                    error_message=str(exc) or "无法连接",
                    redirects=redirects,
                )
            except httpx.HTTPError as exc:
                if verify and is_cert_verification_error(exc):
                    return await _probe_without_cert_check(
                        url,
                        expected_ranges=expected_ranges,
                        cfg=cfg,
                        transport=transport,
                        cert_error=str(exc) or "证书校验失败",
                    )
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


async def _probe_without_cert_check(
    url: str,
    *,
    expected_ranges: list[str] | None,
    cfg: ProbeConfig,
    transport: httpx.AsyncBaseTransport | None,
    cert_error: str,
) -> ProbeResult:
    """证书不被信任时，跳过校验再试一次，区分「锁不配钥匙」与「门都没开」。

    - 跳过校验后拿到响应 → 状态照常按 HTTP 码判定（可达/需认证/状态异常），
      证书的问题由 TLS 维度单独报，这里只在 payload 里留底。
    - 跳过校验后依然连不上 → 真的不可达，保留这次的网络错误。
    """
    retry = await probe_url(
        url,
        expected_ranges=expected_ranges,
        config=cfg,
        transport=transport,
        verify=False,
    )
    if retry.error_code:
        return ProbeResult(
            state=UrlState.UNREACHABLE,
            method=retry.method,
            error_code=retry.error_code,
            error_message=retry.error_message,
            redirects=retry.redirects,
        )
    return ProbeResult(
        state=retry.state,
        status_code=retry.status_code,
        method=retry.method,
        final_url=retry.final_url,
        redirects=retry.redirects,
        body_bytes=retry.body_bytes,
        truncated=retry.truncated,
        tls_verified=False,
        tls_error=cert_error,
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
        "tls_verified": result.tls_verified,
        "tls_error": result.tls_error,
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
