"""TLS 证书检查（A8）。

用本进程即时生成的证书做断言，不依赖外网。
"""

from __future__ import annotations

import datetime as dt
from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from src.checks.tls_probe import (
    CertInfo,
    TlsResult,
    check_certificate,
    classify,
    parse_certificate,
    to_outcome,
)
from src.models import TlsState


def make_cert(
    *,
    cn: str = "web.duomi77.cn",
    sans: list[str] | None = None,
    days: int = 365,
    now: datetime | None = None,
) -> bytes:
    moment = now or datetime.now(timezone.utc)
    key = ec.generate_private_key(ec.SECP256R1())
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    san_entries = [x509.DNSName(item) for item in (sans or [cn])]
    return (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(moment - timedelta(days=1))
        .not_valid_after(moment + timedelta(days=days))
        .add_extension(x509.SubjectAlternativeName(san_entries), critical=False)
        .sign(key, hashes.SHA256())
        .public_bytes(serialization.Encoding.DER)
    )


def test_parse_certificate_fields() -> None:
    info = parse_certificate(make_cert(days=100, sans=["web.duomi77.cn", "*.duomi77.cn"]))
    assert "web.duomi77.cn" in info.subject
    assert "*.duomi77.cn" in info.sans
    assert info.days_remaining is not None
    assert 98 <= info.days_remaining <= 100
    assert info.fingerprint


def test_classify_valid() -> None:
    info = parse_certificate(make_cert(days=200))
    assert classify(verified=True, cert=info) is TlsState.VALID


def test_classify_expiring_at_30_day_boundary() -> None:
    info = CertInfo(days_remaining=30)
    assert classify(verified=True, cert=info) is TlsState.EXPIRING
    assert classify(verified=True, cert=CertInfo(days_remaining=31)) is TlsState.VALID


def test_classify_expired() -> None:
    assert classify(verified=True, cert=CertInfo(days_remaining=-1)) is TlsState.EXPIRED


def test_classify_unverified_is_invalid_even_if_dates_ok() -> None:
    info = parse_certificate(make_cert(days=300))
    assert classify(verified=False, cert=info) is TlsState.INVALID


def test_classify_without_cert_is_unknown() -> None:
    assert classify(verified=True, cert=None) is TlsState.UNKNOWN


def test_check_certificate_success(monkeypatch) -> None:
    der = make_cert()

    def fake_handshake(host, port, timeout, *, verify):
        return der, True, None

    result = check_certificate("https://web.duomi77.cn:9443/x", handshake=fake_handshake)
    assert result.state is TlsState.VALID
    assert result.port == 9443
    assert result.cert is not None


def test_check_certificate_uses_explicit_port() -> None:
    der = make_cert()

    def fake_handshake(host, port, timeout, *, verify):
        return der, True, None

    result = check_certificate("https://dsh.duomi77.cn:12443/", handshake=fake_handshake)
    assert result.port == 12443
    assert result.host == "dsh.duomi77.cn"


def test_check_certificate_default_port_443() -> None:
    der = make_cert()

    def fake_handshake(host, port, timeout, *, verify):
        return der, True, None

    result = check_certificate("https://x.duomi77.cn/", handshake=fake_handshake)
    assert result.port == 443


def test_check_certificate_verification_failure_keeps_invalid() -> None:
    der = make_cert(days=100)

    def fake_handshake(host, port, timeout, *, verify):
        if verify:
            return b"", False, "证书校验失败: hostname mismatch"
        return der, False, None

    result = check_certificate("https://x.duomi77.cn/", handshake=fake_handshake)
    # 验证失败仍是 invalid，即使能解析出未过期日期
    assert result.state is TlsState.INVALID
    assert result.cert is not None
    assert result.cert.days_remaining and result.cert.days_remaining > 0
    assert result.error_code == "tls_verification_failed"


def test_check_certificate_connection_failure() -> None:
    def fake_handshake(host, port, timeout, *, verify):
        return b"", False, "无法连接: connection refused"

    result = check_certificate("https://x.duomi77.cn/", handshake=fake_handshake)
    assert result.cert is None
    outcome = to_outcome(result)
    assert outcome.check_status.value == "error"
    assert outcome.current_state == TlsState.UNKNOWN.value


def test_non_https_endpoint_not_checked() -> None:
    result = check_certificate("http://192.168.31.73:8097/")
    assert result.state is TlsState.UNKNOWN
    assert result.error_code == "not_https"


def test_same_host_different_port_is_separate_check() -> None:
    seen: list[int] = []

    def fake_handshake(host, port, timeout, *, verify):
        seen.append(port)
        return make_cert(), True, None

    check_certificate("https://web.duomi77.cn:9443/", handshake=fake_handshake)
    check_certificate("https://web.duomi77.cn:12443/", handshake=fake_handshake)
    assert seen == [9443, 12443]


def test_outcome_success_carries_payload() -> None:
    info = parse_certificate(make_cert(days=120, sans=["a.duomi77.cn"]))
    result = TlsResult(
        state=TlsState.VALID, host="a.duomi77.cn", port=443, cert=info
    )
    outcome = to_outcome(result)
    assert outcome.check_status.value == "success"
    assert outcome.payload["sans"] == ["a.duomi77.cn"]
    assert outcome.payload["days_remaining"] > 0


def test_invalid_reason_classification() -> None:
    from src.checks.tls_probe import classify_invalid_reason

    assert classify_invalid_reason("certificate verify failed: self-signed certificate") == "self_signed"
    assert classify_invalid_reason("Hostname mismatch, certificate is not valid for 'x'") == "hostname_mismatch"
    assert classify_invalid_reason("certificate has expired") == "expired_chain"
    assert classify_invalid_reason("unable to get local issuer certificate") == "untrusted_ca"
    assert classify_invalid_reason("something else") == "unknown"


def test_self_signed_results_invalid_with_reason() -> None:
    der = make_cert(days=3000)

    def fake_handshake(host, port, timeout, *, verify):
        if verify:
            return b"", False, "证书校验失败: self-signed certificate"
        return der, False, None

    result = check_certificate("https://dsh.duomi77.cn:12443/", handshake=fake_handshake)
    assert result.state is TlsState.INVALID
    assert result.invalid_reason == "self_signed"
    outcome = to_outcome(result)
    assert outcome.check_status.value == "success"  # 检查完成，只是观测到无效
    assert outcome.payload["invalid_reason"] == "self_signed"
    assert outcome.payload["days_remaining"] > 2900  # 到期时间仍可读
