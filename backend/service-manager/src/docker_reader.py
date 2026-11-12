"""Docker 元数据只读采集（design §2 / §3 组件身份规则）。

硬边界：
- 只调用 version / ping / container list / container inspect
- 绝不调用 exec / logs / archive / image pull / 任何写操作
- 立即把 inspect 投影到白名单字段；原始 inspect 永不落库、永不进日志
- 一次完整扫描成功后才递增 scan generation；中断不发布半份快照
"""

from __future__ import annotations

import ipaddress
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol

from src.models import ComposeFileView, HealthState, MountView, PortView

logger = logging.getLogger(__name__)

_ONEOFF_LABEL = "com.docker.compose.oneoff"
_PROJECT_LABEL = "com.docker.compose.project"
_SERVICE_LABEL = "com.docker.compose.service"
_WORKDIR_LABEL = "com.docker.compose.project.working_dir"
_CONFIGFILES_LABEL = "com.docker.compose.project.config_files"
_CONTAINER_NUMBER_LABEL = "com.docker.compose.container-number"


class DockerUnavailable(RuntimeError):
    """Docker Engine 不可达（不阻断台账启动）。"""


class ContainerReader(Protocol):
    def list_containers(self) -> list[dict[str, Any]]: ...


@dataclass
class ScanResult:
    """一轮完整扫描的结果。"""

    components: list[dict[str, Any]] = field(default_factory=list)
    scan_id: int = 0
    finished_at: str = ""
    warnings: list[str] = field(default_factory=list)
    missing_keys: list[str] = field(default_factory=list)


def _nested_label(labels: dict[str, str], key: str) -> str | None:
    value = labels.get(key)
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def compute_source_key(
    *,
    labels: dict[str, str],
    container_id: str,
) -> tuple[str, bool]:
    """稳定身份（design §3）。

    Compose 常驻容器：nas:compose:{project}:{service}:{number}
    oneoff（`com.docker.compose.oneoff=true`）不自动并入常驻组件。
    缺标签容器：nas:container:{id}——重建后需人工重新关联。
    返回 (source_key, oneoff)。
    """
    oneoff = (labels.get(_ONEOFF_LABEL) or "").strip().lower() == "true"
    project = _nested_label(labels, _PROJECT_LABEL)
    service = _nested_label(labels, _SERVICE_LABEL)
    number = _nested_label(labels, _CONTAINER_NUMBER_LABEL) or "1"
    if project and service:
        key = f"nas:compose:{project}:{service}:{number}"
        return key, oneoff
    short_id = container_id[:12] if container_id else "unknown"
    return f"nas:container:{short_id}", oneoff


def project_from_source_key(source_key: str) -> str | None:
    """从 source_key 反解 compose 项目名。

    nas:compose:{project}:{service}:{number} → {project}
    nas:container:{id} → None（没有 compose 项目，游离容器）
    """
    parts = (source_key or "").split(":")
    if len(parts) >= 4 and parts[0] == "nas" and parts[1] == "compose":
        return parts[2] or None
    return None


def _ip_family(host_ip: str) -> str:
    try:
        address = ipaddress.ip_address(host_ip)
    except ValueError:
        return "ipv4"
    return "ipv6" if address.version == 6 else "ipv4"


def project_ports(
    *,
    ports_payload: Any,
    state: str,
    network_mode: str,
) -> list[PortView]:
    """把 inspect 的 NetworkSettings.Ports / HostConfig.PortBindings 投影成 PortView。

    - host 网络：不自动采集（Docker 没有映射列表）
    - stopped 容器：published 映射标 historical（不算当前占用）
    - 未发布但 exposed：标 exposed（内部端口，不是宿主端口）
    """
    if network_mode == "host":
        return []
    views: list[PortView] = []
    seen: set[tuple[str, int | None, str, str | None]] = set()
    running = state == "running"
    for container_port_key, bindings in sorted((ports_payload or {}).items()):
        container_port, _, raw_protocol = str(container_port_key).partition("/")
        protocol = (raw_protocol or "tcp").strip().lower() or "tcp"
        if protocol not in ("tcp", "udp"):
            protocol = "tcp"
        try:
            container_number = int(container_port)
        except ValueError:
            container_number = None
        if not bindings:
            signature = ("exposed", container_number, protocol, None)
            if signature in seen:
                continue
            seen.add(signature)
            views.append(
                PortView(
                    host_ip="",
                    host_port=None,
                    container_port=container_number,
                    protocol=protocol,
                    address_family="ipv4",
                    network_mode=network_mode,
                    kind="exposed",
                    source="docker",
                )
            )
            continue
        for binding in bindings:
            host_ip = str(binding.get("HostIp") or "0.0.0.0")
            raw_port = binding.get("HostPort")
            try:
                host_port = int(raw_port) if raw_port not in (None, "") else None
            except ValueError:
                host_port = None
            signature = (
                "published" if running else "historical",
                container_number,
                protocol,
                host_port,
            )
            if signature in seen:
                continue
            seen.add(signature)
            views.append(
                PortView(
                    host_ip=host_ip,
                    host_port=host_port,
                    container_port=container_number,
                    protocol=protocol,
                    address_family=_ip_family(host_ip),
                    network_mode=network_mode,
                    kind="published" if running else "historical",
                    source="docker",
                )
            )
    return views


def project_mounts(raw_mounts: Any) -> list[MountView]:
    views: list[MountView] = []
    for item in raw_mounts or []:
        mount_type = str(item.get("Type") or "")
        source = str(item.get("Source") or "")
        destination = str(item.get("Destination") or "")
        if mount_type == "bind":
            kind = "bind"
        elif mount_type == "volume":
            kind = "volume"
        elif mount_type == "tmpfs":
            kind = "tmpfs"
        else:
            kind = "other"
        views.append(
            MountView(
                kind=kind,
                source=source,
                destination=destination,
                read_only=not bool(item.get("RW", True)),
            )
        )
    return views


def project_compose_files(
    *, labels: dict[str, str]
) -> tuple[str | None, list[ComposeFileView]]:
    """config_files 保留原始有序列表；相对路径只有已知绝对 working_dir 才拼接。"""
    raw_workdir = _nested_label(labels, _WORKDIR_LABEL)
    raw_files = _nested_label(labels, _CONFIGFILES_LABEL) or ""
    working_dir = raw_workdir
    if working_dir and not working_dir.startswith("/"):
        # 相对 working_dir 本身就是未知位置
        working_dir = None
    files: list[ComposeFileView] = []
    for raw in [item.strip() for item in raw_files.split(",") if item.strip()]:
        if raw.startswith("/"):
            files.append(
                ComposeFileView(raw=raw, resolved=raw, path_state="absolute")
            )
        elif working_dir:
            joined = f"{working_dir.rstrip('/')}/{raw}"
            files.append(
                ComposeFileView(
                    raw=raw, resolved=joined, path_state="relative_resolved"
                )
            )
        else:
            files.append(
                ComposeFileView(
                    raw=raw, resolved=None, path_state="relative_unknown"
                )
            )
    return working_dir, files


_HEALTH_MAP = {
    "healthy": HealthState.HEALTHY,
    "unhealthy": HealthState.UNHEALTHY,
    "starting": HealthState.STARTING,
    "": HealthState.NOT_CONFIGURED,
}


def project_health(state_block: Any) -> HealthState:
    """Docker health 来自 State.Health.Status（不是容器 State.Status）。

    没有 Health 块 = 未配置健康检查 → not_configured，页面不能写「健康」。
    """
    if not isinstance(state_block, dict):
        return HealthState.UNKNOWN
    health_block = state_block.get("Health")
    if not isinstance(health_block, dict):
        return HealthState.NOT_CONFIGURED
    status = str(health_block.get("Status") or "").strip().lower()
    if status in ("", "none"):
        return HealthState.NOT_CONFIGURED
    return _HEALTH_MAP.get(status, HealthState.UNKNOWN)


_HEX_ID_RE = re.compile(r"^[0-9a-f]{12,64}$")


def project_container(payload: dict[str, Any]) -> dict[str, Any]:
    """把一份 inspect（或 list 合成体）投影到白名单字段。

    白名单：id/name/image/labels(仅 compose 四项)/state/health/network_mode/
    ports/mounts。绝不带 Env / Cmd / Secret / 原始 inspect。
    """
    container_id = str(payload.get("Id") or "")
    name = str(payload.get("Name") or "").lstrip("/")
    config = payload.get("Config") or {}
    labels = config.get("Labels") or {}
    if not isinstance(labels, dict):
        labels = {}
    state_block = payload.get("State") or {}
    state = str(state_block.get("Status") or "").lower()
    if not state:
        state = str(payload.get("State") or "").lower() or "unknown"
    host_config = payload.get("HostConfig") or {}
    network_mode = str(host_config.get("NetworkMode") or "bridge")
    networks = (payload.get("NetworkSettings") or {}).get("Networks") or {}
    if network_mode in ("", "default"):
        network_mode = "bridge"
    source_key, oneoff = compute_source_key(labels=labels, container_id=container_id)
    working_dir, compose_files = project_compose_files(labels=labels)
    image_ref = str(config.get("Image") or "")
    image_id = str(payload.get("Image") or "")
    ports_payload = (payload.get("NetworkSettings") or {}).get("Ports") or {}
    return {
        "source_key": source_key,
        "project": _nested_label(labels, _PROJECT_LABEL),
        "service_name": _nested_label(labels, _SERVICE_LABEL),
        "container_id": container_id,
        "container_name": name,
        "image_ref": image_ref,
        "image_id": image_id if _HEX_ID_RE.match(image_id or "") else "",
        "state": state or "unknown",
        "health": project_health(state_block).value,
        "network_mode": network_mode,
        "ports": [
            item.model_dump() for item in project_ports(
                ports_payload=ports_payload, state=state, network_mode=network_mode
            )
        ],
        "mounts": [item.model_dump() for item in project_mounts(payload.get("Mounts"))],
        "compose_working_dir": working_dir,
        "compose_files": [item.model_dump() for item in compose_files],
        "oneoff": oneoff,
        "networks": sorted(networks.keys()) if isinstance(networks, dict) else [],
    }


class DockerClient:
    """docker SDK 的薄封装：自动 API 协商 + 超时，只读。"""

    def __init__(self, base_url: str, *, timeout: float = 5.0) -> None:
        self.base_url = base_url
        self.timeout = timeout

    def _client(self):
        try:
            import docker  # 局部导入：无 Docker 环境下台账仍可用
        except ImportError as exc:  # pragma: no cover - 依赖缺失
            raise DockerUnavailable("docker SDK 未安装") from exc
        try:
            client = docker.DockerClient(
                base_url=self.base_url, timeout=self.timeout, version="auto"
            )
            return client
        except Exception as exc:  # noqa: BLE001 - SDK 异常种类多
            raise DockerUnavailable(str(exc)) from exc

    def ping(self) -> dict[str, Any]:
        client = self._client()
        try:
            info = client.version()
        except Exception as exc:  # noqa: BLE001
            raise DockerUnavailable(str(exc)) from exc
        finally:
            try:
                client.close()
            except Exception:  # noqa: BLE001, S110
                pass
        return {
            "api_version": info.get("ApiVersion"),
            "version": info.get("Version"),
        }

    def list_containers(self) -> list[dict[str, Any]]:
        client = self._client()
        try:
            containers = client.containers.list(all=True)
            payloads: list[dict[str, Any]] = []
            for container in containers:
                try:
                    payloads.append(container.attrs)
                except Exception as exc:  # noqa: BLE001
                    raise DockerUnavailable(
                        f"容器 {getattr(container, 'name', '?')} 读取失败: {exc}"
                    ) from exc
            return payloads
        except DockerUnavailable:
            raise
        except Exception as exc:  # noqa: BLE001
            raise DockerUnavailable(str(exc)) from exc
        finally:
            try:
                client.close()
            except Exception:  # noqa: BLE001, S110
                pass


def scan(
    reader: ContainerReader,
    *,
    scan_id: int,
    now: datetime | None = None,
) -> ScanResult:
    """跑一轮完整扫描。任何异常都不发布半份快照（由调用方处理）。"""
    payloads = reader.list_containers()
    finished = (now or datetime.now(timezone.utc)).isoformat(timespec="seconds")
    components = [project_container(payload) for payload in payloads]
    return ScanResult(components=components, scan_id=scan_id, finished_at=finished)
