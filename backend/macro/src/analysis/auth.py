"""Seven-day password unlock, scoped to the paid analysis API."""
import hashlib
import hmac
import secrets
import time
from collections import defaultdict, deque
from urllib.parse import urlsplit

from fastapi import HTTPException, Request
from src.config import get_settings

COOKIE = "macro_analysis_unlock"
LIFETIME = 7 * 24 * 60 * 60
_revoked: dict[str, float] = {}
_attempts: dict[str, deque] = defaultdict(deque)


def signing_key() -> bytes:
    settings = get_settings()
    if not settings.analysis_password or not settings.analysis_signing_secret:
        raise HTTPException(503, "分析密码与签名密钥尚未配置")
    return hmac.digest(settings.analysis_signing_secret.encode(), settings.analysis_password.encode(), "sha256")


def issue_token() -> str:
    payload = f"{secrets.token_hex(16)}.{int(time.time()) + LIFETIME}"
    return f"{payload}.{hmac.new(signing_key(), payload.encode(), hashlib.sha256).hexdigest()}"


def owner(request: Request) -> str:
    token = request.cookies.get(COOKIE, "")
    try:
        identity, expiry, signature = token.split(".")
        expected = hmac.new(signing_key(), f"{identity}.{expiry}".encode(), hashlib.sha256).hexdigest()
        if int(expiry) <= time.time() or not hmac.compare_digest(signature, expected) or identity in _revoked:
            raise ValueError()
        return identity
    except (ValueError, TypeError):
        raise HTTPException(401, "请先输入分析密码解锁") from None


def revoke(identity: str) -> None:
    now = time.time()
    for key in list(_revoked):
        if _revoked[key] <= now:
            del _revoked[key]
    _revoked[identity] = now + LIFETIME


def check_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    if not origin:
        return  # API clients still require the signed cookie.
    parsed = urlsplit(origin)
    host = request.headers.get("host", "")
    local = {"localhost", "127.0.0.1", "::1"}
    if parsed.netloc != host and not (
        not get_settings().analysis_cookie_secure
        and parsed.hostname in local and request.url.hostname in local
    ):
        raise HTTPException(403, "分析请求来源不匹配")


def check_attempt(key: str, limit: int = 5) -> None:
    now = time.monotonic()
    for old_key in list(_attempts):
        if not _attempts[old_key] or _attempts[old_key][-1] < now - 60:
            del _attempts[old_key]
    bucket = _attempts[key]
    while bucket and bucket[0] < now - 60:
        bucket.popleft()
    if len(bucket) >= limit:
        raise HTTPException(429, "请求过于频繁，请一分钟后重试")
    bucket.append(now)
