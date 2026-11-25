"""写请求同源校验（原认证 A13 中与登录无关的 CSRF 部分）。"""

from __future__ import annotations


from src.auth import normalize_origin
from src.config import Settings
from src.errors import ApiError


def make_request(*, host: str, scheme: str = "https", client=("127.0.0.1", 5000)):
    """构造一个最小可用的 ASGI Request（Request.url 需要 path/query_string/server）。"""
    from starlette.requests import Request

    return Request(
        {
            "type": "http",
            "method": "POST",
            "scheme": scheme,
            "path": "/api/services/services",
            "raw_path": b"/api/services/services",
            "query_string": b"",
            "root_path": "",
            "headers": [(b"host", host.encode())],
            "client": client,
            "server": ("127.0.0.1", 9443),
        }
    )





def test_normalize_origin_strips_path_and_case() -> None:
    assert normalize_origin("HTTPS://Example.COM:443/path") == "https://example.com:443"




def test_origin_allowlist_includes_configured_extras() -> None:
    settings = Settings(
        SERVICE_MANAGER_DATA_DIR="/tmp/x",
        SERVICE_MANAGER_PUBLIC_ORIGIN="https://a.example",
        SERVICE_MANAGER_ALLOWED_ORIGINS="https://b.example, https://a.example",
    )
    assert settings.origin_allowlist == ("https://a.example", "https://b.example")


def test_origin_same_host_passes() -> None:
    from src.auth import _origin_matches_host

    request = make_request(host="127.0.0.1:3012", scheme="http")
    assert _origin_matches_host("http://127.0.0.1:3012", request) is True
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


def test_origin_accepts_host_without_port() -> None:
    """反代 `$host` 不含端口、浏览器 Origin 含端口时也须同源。

    这是生产实测踩到的坑：nginx `$host` 是去端口的 host 名，
    Origin 却是 https://host:port → 字面不等 → 写操作全 401。
    """
    from src.auth import _origin_matches_host

    request = make_request(host="127.0.0.1", scheme="https")
    assert _origin_matches_host("https://127.0.0.1:9443", request) is True
    assert _origin_matches_host("https://127.0.0.1", request) is True
    # 跨站仍拒绝
    assert _origin_matches_host("https://evil.example:9443", request) is False


def test_origin_requires_same_scheme_when_port_differs() -> None:
    from src.auth import _origin_matches_host

    request = make_request(host="web.duomi77.cn", scheme="https")
    assert _origin_matches_host("https://web.duomi77.cn:9443", request) is True
    assert _origin_matches_host("http://web.duomi77.cn:9443", request) is False


def test_origin_with_port_in_host_still_matches() -> None:
    from src.auth import _origin_matches_host

    request = make_request(host="web.duomi77.cn:9443", scheme="https")
    assert _origin_matches_host("https://web.duomi77.cn:9443", request) is True
