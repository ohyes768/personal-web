"""HTTP 可访问性探测（A7）。"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from src.checks.http_probe import ProbeConfig, ProbeResult, classify_status, probe_url
from src.models import UrlState


def run(coro):
    return asyncio.run(coro)


def transport(handler) -> httpx.MockTransport:
    return httpx.MockTransport(handler)


def test_status_classification() -> None:
    assert classify_status(200) is UrlState.REACHABLE
    assert classify_status(302) is UrlState.REACHABLE
    assert classify_status(401) is UrlState.AUTH_REQUIRED
    assert classify_status(403) is UrlState.AUTH_REQUIRED
    assert classify_status(404) is UrlState.UNEXPECTED_STATUS
    assert classify_status(500) is UrlState.UNEXPECTED_STATUS


def test_expected_range_overrides_default() -> None:
    assert classify_status(404, ["404"]) is UrlState.REACHABLE
    assert classify_status(404, ["200-399"]) is UrlState.UNEXPECTED_STATUS


def test_ok_200() -> None:
    result = run(
        probe_url(
            "https://web.duomi77.cn:9443/dividend",
            transport=transport(lambda request: httpx.Response(200)),
        )
    )
    assert result.state is UrlState.REACHABLE
    assert result.status_code == 200
    assert result.method == "HEAD"


def test_401_is_auth_required() -> None:
    result = run(
        probe_url(
            "https://dsh.duomi77.cn:12443/",
            transport=transport(lambda request: httpx.Response(401)),
        )
    )
    assert result.state is UrlState.AUTH_REQUIRED


def test_404_is_unexpected_status_not_unreachable() -> None:
    result = run(
        probe_url("https://x/y", transport=transport(lambda request: httpx.Response(404)))
    )
    assert result.state is UrlState.UNEXPECTED_STATUS
    assert result.status_code == 404


def test_head_405_falls_back_to_get() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.method)
        if request.method == "HEAD":
            return httpx.Response(405)
        return httpx.Response(200)

    result = run(probe_url("https://x/y", transport=transport(handler)))
    assert seen == ["HEAD", "GET"]
    assert result.state is UrlState.REACHABLE
    assert result.method == "GET"


def test_get_body_truncated_at_64k() -> None:
    big = b"x" * (200 * 1024)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "HEAD":
            return httpx.Response(501)
        return httpx.Response(200, content=big)

    result = run(probe_url("https://x/y", transport=transport(handler)))
    assert result.state is UrlState.REACHABLE
    assert result.body_bytes <= 64 * 1024


def test_timeout_is_unreachable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timeout")

    result = run(probe_url("https://x/y", transport=transport(handler)))
    assert result.state is UrlState.UNREACHABLE
    assert result.error_code == "timeout"


def test_connect_error_is_unreachable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    result = run(probe_url("https://x/y", transport=transport(handler)))
    assert result.state is UrlState.UNREACHABLE
    assert result.error_code == "connect_error"


CERT_ERROR_TEXT = (
    "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: "
    "self-signed certificate (_ssl.c:1011)"
)


def test_self_signed_cert_is_not_reported_as_unreachable() -> None:
    """自签证书：跳过校验后能答话 → 可达（证书问题归 TLS 维度）。"""
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if len(calls) == 1:
            raise httpx.ConnectError(CERT_ERROR_TEXT)
        return httpx.Response(200)

    result = run(probe_url("https://x/y", transport=transport(handler)))
    assert result.state is UrlState.REACHABLE
    assert result.status_code == 200
    assert result.tls_verified is False
    assert "self-signed" in (result.tls_error or "")
    assert len(calls) == 2


def test_cert_error_without_working_retry_stays_unreachable() -> None:
    """跳过校验后仍连不上 → 真的不可达。"""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(CERT_ERROR_TEXT)

    result = run(probe_url("https://x/y", transport=transport(handler)))
    assert result.state is UrlState.UNREACHABLE
    assert result.error_code == "connect_error"


def test_plain_connect_error_is_not_retried() -> None:
    """网络不通不该触发重试（重试只会浪费时间）。"""
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        raise httpx.ConnectError("connection refused")

    result = run(probe_url("https://x/y", transport=transport(handler)))
    assert result.state is UrlState.UNREACHABLE
    assert len(calls) == 1


def test_outcome_payload_records_that_cert_check_was_skipped() -> None:
    from src.checks.common import CheckStatus
    from src.checks.http_probe import to_outcome

    outcome = to_outcome(
        ProbeResult(
            state=UrlState.REACHABLE,
            status_code=200,
            method="HEAD",
            tls_verified=False,
            tls_error=CERT_ERROR_TEXT,
        )
    )
    assert outcome.check_status is CheckStatus.SUCCESS
    assert outcome.current_state == "reachable"
    assert outcome.payload["tls_verified"] is False
    assert "self-signed" in outcome.payload["tls_error"]


def test_cert_verification_error_detection() -> None:
    from src.checks.http_probe import is_cert_verification_error

    assert is_cert_verification_error(httpx.ConnectError(CERT_ERROR_TEXT)) is True
    assert is_cert_verification_error(httpx.ConnectError("connection refused")) is False
    assert is_cert_verification_error(None) is False


def test_redirect_chain_followed_within_limit() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/a":
            return httpx.Response(302, headers={"location": "/b"})
        if request.url.path == "/b":
            return httpx.Response(301, headers={"location": "/c"})
        return httpx.Response(200)

    result = run(probe_url("https://x/a", transport=transport(handler)))
    assert result.state is UrlState.REACHABLE
    assert result.redirects == 2


def test_redirect_limit_enforced() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "/loop"})

    result = run(
        probe_url(
            "https://x/start",
            transport=transport(handler),
            config=ProbeConfig(max_redirects=2),
        )
    )
    assert result.state is UrlState.UNREACHABLE
    assert result.error_code == "too_many_redirects"


def test_redirect_to_localhost_rejected() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "http://localhost:9999/admin"})

    result = run(probe_url("https://x/start", transport=transport(handler)))
    assert result.state is UrlState.UNREACHABLE
    assert result.error_code == "loopback_target"


def test_redirect_to_metadata_rejected() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "http://169.254.169.254/latest"})

    result = run(probe_url("https://x/start", transport=transport(handler)))
    assert result.state is UrlState.UNREACHABLE
    assert result.error_code == "invalid_redirect"


def test_localhost_target_refused_before_request() -> None:
    called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200)

    result = run(probe_url("http://localhost:3003/", transport=transport(handler)))
    assert called is False
    assert result.state is UrlState.UNKNOWN
    assert result.error_code == "loopback_target"


def test_non_http_scheme_rejected() -> None:
    from src.errors import ApiError

    with pytest.raises(ApiError):
        run(probe_url("ftp://x/y"))


def test_concurrency_cap_configured() -> None:
    assert ProbeConfig().concurrency == 4
    assert ProbeConfig().timeout == 10.0
