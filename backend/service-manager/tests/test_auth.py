"""认证与 API 边界（A13）。"""

from __future__ import annotations

import pytest

from src.auth import AuthService, COOKIE_NAME, normalize_origin
from src.config import Settings
from src.errors import ApiError


def make_auth(**kwargs) -> AuthService:
    defaults = {
        "password": "pw",
        "secret": "secret",
        "session_hours": 12,
        "secure_cookie": False,
        "origin_allowlist": ("https://dsh.example",),
    }
    defaults.update(kwargs)
    return AuthService(**defaults)


def test_password_uses_constant_time_compare() -> None:
    auth = make_auth()
    assert auth.verify_password("pw") is True
    assert auth.verify_password("pW") is False


def test_login_rate_limited_after_five_attempts() -> None:
    auth = make_auth()
    for _ in range(5):
        auth.limiter.check("1.2.3.4")
    with pytest.raises(ApiError) as exc:
        auth.limiter.check("1.2.3.4")
    assert exc.value.status_code == 429


def test_login_rate_limit_isolated_per_source() -> None:
    auth = make_auth()
    for _ in range(5):
        auth.limiter.check("1.2.3.4")
    auth.limiter.check("5.6.7.8")  # 不应触发


def test_normalize_origin_strips_path_and_case() -> None:
    assert normalize_origin("HTTPS://Example.COM:443/path") == "https://example.com:443"


def test_origin_allowlist_normalized() -> None:
    auth = make_auth(origin_allowlist=("https://dsh.example/",))
    assert auth.origin_allowlist == ("https://dsh.example",)


def test_settings_requires_password_and_secret() -> None:
    with pytest.raises(ValueError):
        Settings(
            SERVICE_MANAGER_ADMIN_PASSWORD="",
            SERVICE_MANAGER_SESSION_SECRET="x",
            SERVICE_MANAGER_DATA_DIR="/tmp/x",
        )
    with pytest.raises(ValueError):
        Settings(
            SERVICE_MANAGER_ADMIN_PASSWORD="x",
            SERVICE_MANAGER_SESSION_SECRET="",
            SERVICE_MANAGER_DATA_DIR="/tmp/x",
        )


def test_origin_allowlist_includes_configured_extras() -> None:
    settings = Settings(
        SERVICE_MANAGER_ADMIN_PASSWORD="p",
        SERVICE_MANAGER_SESSION_SECRET="s",
        SERVICE_MANAGER_DATA_DIR="/tmp/x",
        SERVICE_MANAGER_PUBLIC_ORIGIN="https://a.example",
        SERVICE_MANAGER_ALLOWED_ORIGINS="https://b.example, https://a.example",
    )
    assert settings.origin_allowlist == ("https://a.example", "https://b.example")


def test_origin_same_host_passes() -> None:
    from starlette.requests import Request

    from src.auth import _origin_matches_host

    scope = {
        "type": "http",
        "method": "POST",
        "headers": [(b"host", b"127.0.0.1:3012")],
    }
    request = Request(scope)
    assert _origin_matches_host("http://127.0.0.1:3012", request) is True
    assert _origin_matches_host("http://127.0.0.1:9999", request) is False
    assert _origin_matches_host("https://evil.example", request) is False


def test_origin_default_port_normalization() -> None:
    from starlette.requests import Request

    from src.auth import _origin_matches_host

    scope = {"type": "http", "method": "POST", "headers": [(b"host", b"web.duomi77.cn:443")]}
    request = Request(scope)
    assert _origin_matches_host("https://web.duomi77.cn", request) is True


def test_forwarded_host_trusted_only_from_loopback() -> None:
    from starlette.requests import Request

    from src.auth import _origin_matches_forwarded_host

    loopback_scope = {
        "type": "http",
        "method": "POST",
        "client": ("127.0.0.1", 5000),
        "headers": [(b"x-forwarded-host", b"127.0.0.1:3013")],
    }
    assert (
        _origin_matches_forwarded_host("http://127.0.0.1:3013", Request(loopback_scope))
        is True
    )
    remote_scope = {
        "type": "http",
        "method": "POST",
        "client": ("203.0.113.9", 5000),
        "headers": [(b"x-forwarded-host", b"127.0.0.1:3013")],
    }
    assert (
        _origin_matches_forwarded_host("http://127.0.0.1:3013", Request(remote_scope))
        is False
    )


def _issue_headers(**overrides) -> str:
    from starlette.responses import Response

    params = {
        "password": "pw",
        "secret": "secret",
        "session_hours": 12,
        "secure_cookie": True,
        "origin_allowlist": ("https://dsh.example",),
    }
    params.update(overrides)
    auth = AuthService(**params)
    response = Response()
    auth.issue(response)
    return response.headers["set-cookie"]


def test_session_cookie_attributes_are_hardened() -> None:
    """design §7：HttpOnly + SameSite=Strict + Path=/api；生产带 Secure。"""
    header = _issue_headers()
    # starlette 输出的小写形式：... HttpOnly; Max-Age=...; Path=/api; SameSite=strict; Secure
    assert "HttpOnly" in header
    assert "samesite=strict" in header.lower()
    assert "Path=/api" in header
    assert "; Secure" in header


def test_session_cookie_path_covers_backend_direct_api() -> None:
    """Path 必须是 /api：写 /api/services 会让后端直连/开发 rewrite 全部 401。"""
    header = _issue_headers()
    assert "Path=/api;" in header or header.rstrip().endswith("Path=/api")
    assert "Path=/api/services" not in header


def test_session_cookie_secure_dropped_for_local_http() -> None:
    header = _issue_headers(secure_cookie=False)
    assert "Secure" not in header


def test_session_cookie_is_signed_and_not_plaintext() -> None:
    header = _issue_headers()
    assert "sm_session=" in header
    token = header.split("sm_session=", 1)[1].split(";", 1)[0]
    # 签名 token 形如 <payload>.<timestamp>.<signature>，不能直接暴露主体名
    assert token.count(".") == 2
    assert "admin" not in token.split(".")[0]
