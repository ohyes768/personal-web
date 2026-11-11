"""URL 解析与校验（design §5 / §6）。

职责：
- 只接受 http/https，拒绝 userinfo（`user:pass@host`）与敏感凭据查询参数
- 区分「浏览器打开用的 url」与「后端探测用的 probe_url」
- 识别 IP 入口、解析显式端口、拒绝云元数据地址
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlsplit

from src.errors import bad_request

_SENSITIVE_QUERY_KEYS = {
    "token",
    "access_token",
    "api_key",
    "apikey",
    "key",
    "secret",
    "password",
    "passwd",
    "pwd",
    "sig",
    "signature",
    "auth",
    "code",
}

# 云元数据地址：探测目标一律拒绝（design §6）
_BLOCKED_HOSTS = {
    "169.254.169.254",
    "metadata.google.internal",
    "100.100.100.200",
}


@dataclass(frozen=True)
class ParsedUrl:
    raw: str
    scheme: str
    host: str
    port: int | None
    path: str
    query: str
    is_ip: bool
    effective_port: int

    @property
    def origin(self) -> str:
        suffix = f":{self.port}" if self.port is not None else ""
        return f"{self.scheme}://{self.host}{suffix}"

    @property
    def cert_key(self) -> tuple[str, int]:
        return (self.host.lower(), self.effective_port)


def is_ip_host(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


def parse_http_url(raw: str, *, field: str = "url", allow_blocked: bool = False) -> ParsedUrl:
    """解析并校验一个 HTTP(S) URL。

    allow_blocked：登记「浏览器打开」入口时，元数据地址仍不允许，
    但这里留出显式开关便于测试用例断言拒绝路径。
    """
    text = (raw or "").strip()
    if not text:
        raise bad_request("URL 不能为空", {field: "URL 不能为空"})
    parts = urlsplit(text)
    if parts.scheme not in ("http", "https"):
        raise bad_request(
            "只支持 http/https 入口", {field: "只支持 http/https"}
        )
    if parts.username or parts.password:
        raise bad_request(
            "URL 不能包含账号密码", {field: "URL 不能包含账号密码"}
        )
    host = parts.hostname or ""
    if not host:
        raise bad_request("URL 缺少主机名", {field: "URL 缺少主机名"})
    lowered = host.lower()
    if not allow_blocked and lowered in _BLOCKED_HOSTS:
        raise bad_request(
            "云元数据地址不允许作为入口", {field: "云元数据地址不允许"}
        )
    for key, _value in parse_qsl(parts.query, keep_blank_values=True):
        if key.lower() in _SENSITIVE_QUERY_KEYS:
            raise bad_request(
                "URL 不能包含凭据类查询参数",
                {field: "URL 不能包含凭据类查询参数"},
            )
    try:
        port = parts.port
    except ValueError as exc:  # 端口非法
        raise bad_request("URL 端口不合法", {field: "URL 端口不合法"}) from exc
    effective = port if port is not None else (443 if parts.scheme == "https" else 80)
    return ParsedUrl(
        raw=text,
        scheme=parts.scheme,
        host=host,
        port=port,
        path=parts.path or "/",
        query=parts.query,
        is_ip=is_ip_host(host),
        effective_port=effective,
    )


def is_loopback_host(host: str) -> bool:
    """探测目标不能是 localhost —— 容器内 localhost 指管理台自身。"""
    lowered = host.lower()
    if lowered in ("localhost", "localhost.localdomain"):
        return True
    try:
        address = ipaddress.ip_address(lowered)
    except ValueError:
        return False
    return address.is_loopback or address.is_unspecified


def validate_probe_url(raw: str, *, field: str = "probe_url") -> ParsedUrl:
    parsed = parse_http_url(raw, field=field)
    if is_loopback_host(parsed.host):
        raise bad_request(
            "探测地址不能是 localhost（容器内 localhost 指管理台自身），"
            "请填写 NAS 可达地址或同网络容器名",
            {field: "探测地址不能是 localhost"},
        )
    return parsed
