"""端口 / 域名 / 证书投影（design §5）。

核心口径（A5/A6）：
- 端口总览覆盖全部发现组件（含未导入和已忽略），支持「仅已登记服务」筛选
- 仅当同主机、同协议、同地址族、且 IP 绑定重叠时才提示「潜在重叠」
  - 0.0.0.0 与具体 IPv4 相交；IPv6 通配只在 IPv6 内比较；跨族标未判断
- 容器内部 expose 的同一端口出现在多个容器上不算主机冲突
- stopped 容器端口标 historical，不算当前有效占用；host 网络标未采集
- 页面永久注明「不包含宿主进程全部监听，不能据此证明端口空闲」
- 域名从 endpoint 推导，不另建需要手工同步的域名表
- 证书按 host+port 去重，同域名不同端口不混用
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from typing import Any

from src.db import Store
from src.discovery import DiscoveryService
from src.models import (
    CertificateOverviewRow,
    CheckView,
    DomainOverviewRow,
    EndpointKind,
    PortNoteRecord,
    PortOverviewRow,
    PortView,
    TlsState,
)
from src.registry import Registry
from src.urls import parse_http_url

PORT_SCOPE_NOTE = (
    "端口总览只覆盖 Docker 发布/内部端口与人工登记端口，不包含宿主进程的全部监听，"
    "不能据此证明端口空闲。"
)


def _is_ipv4_address(value: str) -> bool:
    try:
        return ipaddress.ip_address(value).version == 4
    except ValueError:
        return False


def _is_ipv6_address(value: str) -> bool:
    try:
        return ipaddress.ip_address(value).version == 6
    except ValueError:
        return False


def binding_covers(wide: str, narrow: str) -> bool:
    """wide 绑定的 IP 是否覆盖 narrow。

    - 空串 / 0.0.0.0 → 覆盖全部 IPv4
    - :: / [::] → 覆盖全部 IPv6
    - 具体地址只覆盖自身
    """
    if wide in ("", "0.0.0.0"):
        return _is_ipv4_address(narrow) or narrow in ("", "0.0.0.0")
    if wide in ("::", "[::]", "::0"):
        return _is_ipv6_address(narrow) or narrow in ("::", "[::]", "::0")
    return wide == narrow


def ports_overlap(left: PortView, right: PortView) -> bool:
    """同主机、同协议、同地址族、IP 绑定重叠 + 同宿主端口。"""
    if left.protocol != right.protocol:
        return False
    if left.address_family != right.address_family:
        return False
    if left.host_port is None or right.host_port is None:
        return False
    if not left.host_port == right.host_port:
        return False
    return binding_covers(left.host_ip, right.host_ip) or binding_covers(
        right.host_ip, left.host_ip
    )


def find_potential_overlaps(rows: list[PortOverviewRow]) -> list[tuple[str, str]]:
    """只返回「有效发布 / 人工规划」端口之间的重叠对。

    exposed（容器内部）不参与；historical（stopped）不参与。
    """
    effective = [
        row
        for row in rows
        if row.kind in ("published",) or (row.kind == "exposed" and row.origin == "manual")
    ]
    pairs: list[tuple[str, str]] = []
    for index, left in enumerate(effective):
        for right in effective[index + 1 :]:
            if left is right:
                continue
            if ports_overlap(left, right):
                label_left = left.source_key or left.note or f"manual:{left.host_port}"
                label_right = right.source_key or right.note or f"manual:{right.host_port}"
                if label_left != label_right:
                    pairs.append((label_left, label_right))
    return pairs


@dataclass
class ServiceBinding:
    service_id: str
    required: bool
    label: str


class ResourceProjector:
    def __init__(self, registry: Registry, discovery: DiscoveryService) -> None:
        self.registry = registry
        self.discovery = discovery

    # -- 端口 ------------------------------------------------------------

    def ports(
        self,
        *,
        only_registered: bool = False,
        query: str = "",
        protocol: str = "",
    ) -> dict[str, Any]:
        components = self.discovery.components()
        bindings = self.registry.binding_map()
        services = self._service_names()
        rows: list[PortOverviewRow] = []
        for source_key, component in components.items():
            binding = bindings.get(source_key)
            if only_registered and binding is None:
                continue
            for port in component.get("ports", []):
                view = PortView(**port)
                rows.append(
                    PortOverviewRow(
                        **view.model_dump(),
                        source_key=source_key,
                        container_name=component.get("container_name", ""),
                        project=component.get("project"),
                        service_id=binding[0] if binding else None,
                        service_name=services.get(binding[0]) if binding else None,
                        note="",
                        origin="docker",
                    )
                )
        for note in self.registry.list_port_notes():
            if only_registered:
                pass
            rows.append(self._note_to_row(note, services))
        if protocol:
            rows = [row for row in rows if row.protocol == protocol]
        if query:
            needle = query.lower()
            rows = [
                row
                for row in rows
                if needle
                in " ".join(
                    [
                        str(row.container_name or ""),
                        str(row.project or ""),
                        str(row.service_name or ""),
                        str(row.host_port or ""),
                        str(row.container_port or ""),
                        row.host_ip,
                        row.note,
                    ]
                ).lower()
            ]
        rows.sort(
            key=lambda row: (
                row.host_port if row.host_port is not None else 1 << 30,
                row.protocol,
                row.host_ip,
                row.container_name,
            )
        )
        overlaps = find_potential_overlaps(rows)
        return {
            "items": [row.model_dump() for row in rows],
            "overlaps": [{"left": left, "right": right} for left, right in overlaps],
            "scope_note": PORT_SCOPE_NOTE,
        }

    def _note_to_row(
        self, note: PortNoteRecord, services: dict[str, str]
    ) -> PortOverviewRow:
        family = "ipv6" if _is_ipv6_address(note.host_ip.strip("[]")) else "ipv4"
        return PortOverviewRow(
            host_ip=note.host_ip,
            host_port=note.host_port,
            container_port=note.container_port,
            protocol=note.protocol,
            address_family=family,
            network_mode="manual",
            kind="exposed",
            source="manual",
            source_key=None,
            container_name="",
            project=None,
            service_id=note.service_id,
            service_name=services.get(note.service_id),
            note=note.note,
            origin="manual",
        )

    # -- 域名 ------------------------------------------------------------

    def domains(self, *, query: str = "") -> dict[str, Any]:
        services = self._service_names()
        endpoints = self.registry.list_endpoints()
        tls_checks = self._tls_checks()
        rows: list[DomainOverviewRow] = []
        for endpoint in endpoints:
            try:
                parsed = parse_http_url(endpoint.url)
            except Exception:  # noqa: BLE001 - 历史记录里的坏 URL 不阻断投影
                continue
            check = tls_checks.get(endpoint.id)
            state = TlsState.UNKNOWN
            days = None
            if check is not None and check.current_state:
                try:
                    state = TlsState(check.current_state)
                except ValueError:
                    state = TlsState.UNKNOWN
            if check is not None and check.payload:
                days = check.payload.get("days_remaining")
            rows.append(
                DomainOverviewRow(
                    host=parsed.host.lower(),
                    scheme=parsed.scheme,
                    port=parsed.port,
                    path=parsed.path,
                    url=endpoint.url,
                    endpoint_id=endpoint.id,
                    endpoint_label=endpoint.label,
                    endpoint_kind=endpoint.kind,
                    service_id=endpoint.service_id,
                    service_name=services.get(endpoint.service_id, ""),
                    route_target=endpoint.route_target,
                    tls_state=state,
                    tls_days_remaining=days if isinstance(days, int) else None,
                    is_ip=parsed.is_ip,
                )
            )
        if query:
            needle = query.lower()
            rows = [
                row
                for row in rows
                if needle
                in " ".join(
                    [
                        row.host,
                        str(row.port or ""),
                        row.path,
                        row.service_name,
                        row.endpoint_label,
                    ]
                ).lower()
            ]
        rows.sort(key=lambda row: (row.host, row.port or 0, row.path))
        return {"items": [row.model_dump() for row in rows]}

    # -- 证书 ------------------------------------------------------------

    def certificates(self, *, query: str = "") -> dict[str, Any]:
        endpoints = self.registry.list_endpoints()
        tls_checks = self._tls_checks()
        # host+port 去重（同域名不同端口分别检查）
        buckets: dict[tuple[str, int], dict[str, Any]] = {}
        for endpoint in endpoints:
            if not endpoint.tls_check:
                continue
            try:
                parsed = parse_http_url(endpoint.url)
            except Exception:  # noqa: BLE001
                continue
            if parsed.scheme != "https":
                continue
            key = parsed.cert_key
            bucket = buckets.setdefault(
                key,
                {
                    "host": parsed.host.lower(),
                    "port": parsed.effective_port,
                    "used_by": [],
                    "check": tls_checks.get(endpoint.id),
                    "labels": [],
                },
            )
            bucket["used_by"].append(endpoint.id)
            bucket["labels"].append(endpoint.label or endpoint.url)
            if bucket["check"] is None:
                bucket["check"] = tls_checks.get(endpoint.id)
        rows: list[CertificateOverviewRow] = []
        for (host, port), bucket in sorted(buckets.items()):
            check: CheckView | None = bucket["check"]
            payload = (check.payload or {}) if check else {}
            state = TlsState.UNKNOWN
            if check and check.current_state:
                try:
                    state = TlsState(check.current_state)
                except ValueError:
                    state = TlsState.UNKNOWN
            rows.append(
                CertificateOverviewRow(
                    host=host,
                    port=port,
                    tls_state=state,
                    subject=str(payload.get("subject") or ""),
                    issuer=str(payload.get("issuer") or ""),
                    sans=list(payload.get("sans") or []),
                    not_before=payload.get("not_before"),
                    not_after=payload.get("not_after"),
                    days_remaining=payload.get("days_remaining"),
                    fingerprint=str(payload.get("fingerprint") or ""),
                    used_by=sorted(bucket["labels"]),
                    error=(check.error_message if check else None),
                    invalid_reason=payload.get("invalid_reason"),
                )
            )
        if query:
            needle = query.lower()
            rows = [
                row
                for row in rows
                if needle in f"{row.host}:{row.port}".lower()
                or needle in row.subject.lower()
            ]
        return {"items": [row.model_dump() for row in rows]}

    # -- 内部 ------------------------------------------------------------

    def _tls_checks(self) -> dict[str, CheckView]:
        from src.checks.common import CheckStore

        checks: dict[str, CheckView] = {}
        for target_id, kinds in CheckStore(self.registry.store).all_rows(
            target_type="endpoint"
        ).items():
            if "tls" in kinds:
                checks[target_id] = kinds["tls"]
        return checks

    def _service_names(self) -> dict[str, str]:
        with self.registry.store.read() as conn:
            rows = conn.execute("SELECT id, name FROM services").fetchall()
        return {row["id"]: row["name"] for row in rows}
