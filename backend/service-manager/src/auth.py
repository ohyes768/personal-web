"""写请求同源校验（原 design §7 中与登录无关的 CSRF 防御部分）。

认证已整体交给 nginx basic auth（2026-11-25 去除应用内登录口令/会话），
后端仅保留写请求（非 GET/HEAD/OPTIONS）的 Origin 校验，防跨站写操作。
"""

from __future__ import annotations

import ipaddress
from urllib.parse import urlsplit

from fastapi import Request

from src.errors import unauthorized


def check_origin(request: Request, allowlist: tuple[str, ...]) -> None:
    """写请求（非 GET/HEAD/OPTIONS）必须来自同源。

    三条通过路径：
    1. Origin 的 scheme://host:port 与本次请求的 Host 一致（标准 CSRF 防御，
       天然兼容直连 IP、局域网域名和不同端口）；
    2. Origin 与 allowlist（SERVICE_MANAGER_PUBLIC_ORIGIN 及附加项）一致；
    3. Origin 与 X-Forwarded-Host 一致，且直连方是回环地址。仅用于开发期
       Next rewrite（它会把 Host 改写成后端地址，但保留 X-Forwarded-Host）；
       生产 nginx 保留 Host，走第 1 条，不依赖可伪造的头。

    浏览器不发 Origin 时（curl/服务端调用）也拒绝，避免 CSRF 面。
    """
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    origin = request.headers.get("origin")
    if not origin:
        raise unauthorized("缺少 Origin 头")
    normalized = normalize_origin(origin)
    if normalized in allowlist:
        return
    if _origin_matches_host(normalized, request):
        return
    if _origin_matches_forwarded_host(normalized, request):
        return
    raise unauthorized("请求来源不被允许")


def _origin_matches_host(origin: str, request: Request) -> bool:
    """Origin 的 host[:port] 是否等于本次请求的 Host。

    两层判断：
    1. netloc 完全相等（最严格，正常反代都会命中）；
    2. hostname 与 scheme 相同即接受——反代的 `$host` 变量**不含端口**
       （nginx 文档：$host 是去端口的 host 名），而浏览器 Origin 带端口，
       两者字面不等但指向同一个入口。只放宽到 hostname 相同，
       跨站（hostname 不同）依然被拒。
    """
    parts = urlsplit(origin)
    if not parts.scheme or not parts.hostname:
        return False
    host_header = request.headers.get("host", "").strip().lower()
    if not host_header:
        return False
    origin_netloc = parts.netloc.lower()
    if origin_netloc == host_header:
        return True
    # 默认端口省略写法：https://a:443 == https://a
    if parts.port is None:
        default_port = 443 if parts.scheme == "https" else 80
        if host_header == f"{parts.hostname.lower()}:{default_port}":
            return True
    # Host 头部可能带端口，拆出来比 hostname
    host_name = host_header.rsplit(":", 1)[0] if ":" in host_header else host_header
    host_name = host_name.strip("[]")
    if host_name != parts.hostname.lower():
        return False
    # 端口不同时，要求 scheme 一致，避免 http 入口的 Origin 打到 https 入口
    host_scheme = request.url.scheme
    return host_scheme == parts.scheme


def _is_loopback_peer(request: Request) -> bool:
    client = request.client
    if client is None or not client.host:
        return False
    try:
        return ipaddress.ip_address(client.host).is_loopback
    except ValueError:
        return client.host in ("localhost", "testclient")


def _origin_matches_forwarded_host(origin: str, request: Request) -> bool:
    """仅在直连方是回环地址时信任 X-Forwarded-Host（开发期 rewrite 用）。"""
    if not _is_loopback_peer(request):
        return False
    forwarded = (request.headers.get("x-forwarded-host") or "").strip().lower()
    if not forwarded:
        return False
    parts = urlsplit(origin)
    if not parts.netloc:
        return False
    return parts.netloc.lower() == forwarded


def normalize_origin(value: str) -> str:
    parts = urlsplit(value.strip())
    if not parts.scheme or not parts.netloc:
        return value.strip().rstrip("/")
    return f"{parts.scheme.lower()}://{parts.netloc.lower()}"
