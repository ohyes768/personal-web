"""TLS 证书检查（design §6 TLS）。

- 从登记 HTTPS url 的原始 host+port 检查，不从 probe_url 或最终跳转站点代替
- 以 SNI/主机名验证信任链与域名
- 保存 subject/SAN/issuer/有效期/fingerprint
- 30 天内 expiring，过期 expired，域名或信任链不正确 invalid
- 失败时仍可解析公开叶证书的到期时间，但状态保留 invalid

不读取任何私钥、不读本机证书文件、不据「证书可访问」断言续期任务正常。
"""

from __future__ import annotations

import socket
import ssl
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.x509.oid import NameOID

from src.checks.common import CheckOutcome, CheckStatus
from src.models import TlsState
from src.urls import parse_http_url

EXPIRING_THRESHOLD_DAYS = 30
DEFAULT_TIMEOUT = 10.0


@dataclass
class CertInfo:
    subject: str = ""
    issuer: str = ""
    sans: list[str] = field(default_factory=list)
    not_before: str | None = None
    not_after: str | None = None
    days_remaining: int | None = None
    fingerprint: str = ""


@dataclass
class TlsResult:
    state: TlsState
    host: str = ""
    port: int = 443
    cert: CertInfo | None = None
    error_code: str | None = None
    error_message: str | None = None
    # invalid 的原因分类：self_signed / hostname_mismatch / expired_chain /
    # untrusted_ca / unknown。页面据此说明「为什么无效」，而不是只给一个红灯。
    invalid_reason: str | None = None


def classify_invalid_reason(message: str | None) -> str:
    text = (message or "").lower()
    if "self-signed" in text or "self signed" in text:
        return "self_signed"
    if "hostname mismatch" in text or "doesn't match" in text or "not valid for" in text:
        return "hostname_mismatch"
    if "expired" in text or "not yet valid" in text:
        return "expired_chain"
    if "unable to get local issuer" in text or "unknown ca" in text or "untrusted" in text:
        return "untrusted_ca"
    if "certificate verify failed" in text:
        return "untrusted_ca"
    return "unknown"


def _name_to_str(name: x509.Name) -> str:
    parts: list[str] = []
    for oid, label in (
        (NameOID.COMMON_NAME, "CN"),
        (NameOID.ORGANIZATION_NAME, "O"),
    ):
        values = name.get_attributes_for_oid(oid)
        if values:
            parts.append(f"{label}={values[0].value}")
    return ", ".join(parts)


def parse_certificate(der: bytes, *, now: datetime | None = None) -> CertInfo:
    cert = x509.load_der_x509_certificate(der, default_backend())
    moment = now or datetime.now(timezone.utc)
    try:
        not_before = cert.not_valid_before_utc
        not_after = cert.not_valid_after_utc
    except AttributeError:  # 旧版 cryptography
        not_before = cert.not_valid_before.replace(tzinfo=timezone.utc)
        not_after = cert.not_valid_after.replace(tzinfo=timezone.utc)
    sans: list[str] = []
    try:
        extension = cert.extensions.get_extension_for_class(
            x509.SubjectAlternativeName
        )
        sans = [str(item.value) for item in extension.value]
    except x509.ExtensionNotFound:
        sans = []
    remaining = int((not_after - moment).total_seconds() // 86400)
    return CertInfo(
        subject=_name_to_str(cert.subject),
        issuer=_name_to_str(cert.issuer),
        sans=sans,
        not_before=not_before.isoformat(timespec="seconds"),
        not_after=not_after.isoformat(timespec="seconds"),
        days_remaining=remaining,
        fingerprint=cert.fingerprint(hashes.SHA256()).hex(),
    )


def classify(
    *,
    verified: bool,
    cert: CertInfo | None,
    now: datetime | None = None,
    threshold_days: int = EXPIRING_THRESHOLD_DAYS,
) -> TlsState:
    if not verified:
        return TlsState.INVALID
    if cert is None or cert.days_remaining is None:
        return TlsState.UNKNOWN
    if cert.days_remaining < 0:
        return TlsState.EXPIRED
    if cert.days_remaining <= threshold_days:
        return TlsState.EXPIRING
    return TlsState.VALID


def _handshake(host: str, port: int, timeout: float, *, verify: bool) -> tuple[bytes, bool, str | None]:
    """返回 (叶证书 DER, 是否验证通过, 错误信息)。"""
    context = (
        ssl.create_default_context()
        if verify
        else ssl._create_unverified_context()  # noqa: SLF001 - 仅用于失败后取公开叶证书
    )
    error: str | None = None
    try:
        with socket.create_connection((host, port), timeout=timeout) as raw:
            with context.wrap_socket(raw, server_hostname=host) as tls:
                der = tls.getpeercert(binary_form=True)
                return der, True, None
    except ssl.SSLCertVerificationError as exc:
        error = f"证书校验失败: {exc.verify_message or exc}"
    except ssl.SSLError as exc:
        error = f"TLS 握手失败: {exc}"
    except socket.timeout:
        error = "TLS 连接超时"
    except OSError as exc:
        error = f"无法连接: {exc}"
    return b"", False, error


def check_certificate(
    url: str,
    *,
    timeout: float = DEFAULT_TIMEOUT,
    now: datetime | None = None,
    handshake=None,
) -> TlsResult:
    parsed = parse_http_url(url)
    host = parsed.host
    port = parsed.effective_port
    if parsed.scheme != "https":
        return TlsResult(
            state=TlsState.UNKNOWN,
            host=host,
            port=port,
            error_code="not_https",
            error_message="非 HTTPS 入口不做证书检查",
        )
    runner = handshake or _handshake
    der, verified, error = runner(host, port, timeout, verify=True)
    cert = None
    if der:
        try:
            cert = parse_certificate(der, now=now)
        except Exception as exc:  # noqa: BLE001
            error = f"证书解析失败: {exc}"
    if not verified and not der:
        # 验证失败后单独取一次公开叶证书（不信任），仅用于展示到期时间
        fallback_der, _ok, _err = runner(host, port, timeout, verify=False)
        if fallback_der:
            try:
                cert = parse_certificate(fallback_der, now=now)
            except Exception:  # noqa: BLE001 - 解析失败保留 None
                cert = None
    return TlsResult(
        state=classify(verified=verified, cert=cert, now=now),
        host=host,
        port=port,
        cert=cert,
        error_code=None if verified else "tls_verification_failed",
        error_message=error,
        invalid_reason=None if verified else classify_invalid_reason(error),
    )


def to_outcome(result: TlsResult) -> CheckOutcome:
    payload: dict[str, Any] = {
        "state": result.state.value,
        "host": result.host,
        "port": result.port,
        "subject": result.cert.subject if result.cert else "",
        "issuer": result.cert.issuer if result.cert else "",
        "sans": result.cert.sans if result.cert else [],
        "not_before": result.cert.not_before if result.cert else None,
        "not_after": result.cert.not_after if result.cert else None,
        "days_remaining": result.cert.days_remaining if result.cert else None,
        "fingerprint": result.cert.fingerprint if result.cert else "",
        # 状态为 invalid 时给出原因，避免把「自签但没过期」当成「坏证书」
        "invalid_reason": result.invalid_reason,
        "perspective": "probed from service-manager backend",
    }
    # 证书无效/过期/主机名不符都是「完成检查得到的观测」→ check_status=success
    if result.error_code == "not_https":
        return CheckOutcome(
            check_status=CheckStatus.ERROR,
            current_state=result.state.value,
            payload=payload,
            error_code=result.error_code,
            error_message=result.error_message,
        )
    if result.cert is None and result.error_message:
        return CheckOutcome(
            check_status=CheckStatus.ERROR,
            current_state=TlsState.UNKNOWN.value,
            payload={**payload, "state": TlsState.UNKNOWN.value},
            error_code="tls_unreachable",
            error_message=result.error_message,
        )
    return CheckOutcome(
        check_status=CheckStatus.SUCCESS,
        current_state=result.state.value,
        payload=payload,
    )
