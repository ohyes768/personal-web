"""单管理员认证（design §7）。

- 口令常量时间比较
- itsdangerous 签名 session cookie，12 小时有效
- cookie HttpOnly / SameSite=Strict / Path=/api/services
- 写请求校验 Origin（同源 allowlist），禁止 wildcard
- 登录失败按来源限速（5 次/分钟）
"""

from __future__ import annotations

import hmac
import ipaddress
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

from fastapi import Request, Response
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from src.errors import rate_limited, unauthorized

COOKIE_NAME = "sm_session"
# 对外路径是 /api/services/*（nginx 剥前缀到后端 /api/*），cookie 因此要覆盖
# /api 这个共同前缀：既随外部请求发出，也在后端直连/开发 rewrite 下有效。
# 作用域仍然只限本应用的 API，不会发给页面或其他路径。
COOKIE_PATH = "/api"
LOGIN_LIMIT = 5
LOGIN_WINDOW_SECONDS = 60


@dataclass
class SessionInfo:
    subject: str
    expires_at: datetime


class LoginRateLimiter:
    """按来源的滑动窗口限速（进程内存）。"""

    def __init__(self, limit: int = LOGIN_LIMIT, window: float = LOGIN_WINDOW_SECONDS) -> None:
        self.limit = limit
        self.window = window
        self._hits: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def check(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            hits = [item for item in self._hits.get(key, []) if now - item < self.window]
            if len(hits) >= self.limit:
                self._hits[key] = hits
                raise rate_limited("登录尝试过于频繁，请稍后再试")
            hits.append(now)
            self._hits[key] = hits

    def reset(self, key: str) -> None:
        with self._lock:
            self._hits.pop(key, None)


class AuthService:
    def __init__(
        self,
        *,
        password: str,
        secret: str,
        session_hours: int = 12,
        secure_cookie: bool = True,
        origin_allowlist: tuple[str, ...] = (),
    ) -> None:
        self._password = password
        self._secret = secret
        self.session_hours = session_hours
        self.secure_cookie = secure_cookie
        self.origin_allowlist = tuple(
            normalize_origin(item) for item in origin_allowlist if item.strip()
        )
        self._serializer = URLSafeTimedSerializer(secret, salt="service-manager-session")
        self.limiter = LoginRateLimiter()

    # -- 口令 ------------------------------------------------------------

    def verify_password(self, candidate: str) -> bool:
        return hmac.compare_digest(candidate.encode("utf-8"), self._password.encode("utf-8"))

    # -- 会话 ------------------------------------------------------------

    def issue(self, response: Response, *, now: datetime | None = None) -> SessionInfo:
        issued = now or datetime.now(timezone.utc)
        expires = issued + timedelta(hours=self.session_hours)
        token = self._serializer.dumps({"sub": "admin"})
        response.set_cookie(
            key=COOKIE_NAME,
            value=token,
            max_age=self.session_hours * 3600,
            httponly=True,
            samesite="strict",
            secure=self.secure_cookie,
            path=COOKIE_PATH,
        )
        return SessionInfo(subject="admin", expires_at=expires)

    def clear(self, response: Response) -> None:
        response.delete_cookie(COOKIE_NAME, path=COOKIE_PATH)

    def read_session(self, request: Request) -> SessionInfo | None:
        token = request.cookies.get(COOKIE_NAME)
        if not token:
            return None
        try:
            data, issued_at = self._serializer.loads(
                token, max_age=self.session_hours * 3600, return_timestamp=True
            )
        except SignatureExpired:
            return None
        except BadSignature:
            return None
        if not isinstance(data, dict) or data.get("sub") != "admin":
            return None
        expires = issued_at + timedelta(hours=self.session_hours)
        return SessionInfo(subject="admin", expires_at=expires)

    def require_session(self, request: Request) -> SessionInfo:
        info = self.read_session(request)
        if info is None:
            raise unauthorized()
        return info

    def check_origin(self, request: Request) -> None:
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
        if normalized in self.origin_allowlist:
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
