"""API / 投影模型与状态枚举（design §3 / §6）。

状态维度严格分开：runtime / health / url / tls / release 各自独立枚举，
不得用一个绿色图标抹平。所有时间均为 UTC ISO 8601 带时区。
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat(timespec="seconds")


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


# ---------------------------------------------------------------------------
# 枚举
# ---------------------------------------------------------------------------


class RuntimeState(StrEnum):
    RUNNING = "running"
    PARTIAL = "partial"
    STOPPED = "stopped"
    MISSING = "missing"
    UNKNOWN = "unknown"


class HealthState(StrEnum):
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    STARTING = "starting"
    NOT_CONFIGURED = "not_configured"
    UNKNOWN = "unknown"


class UrlState(StrEnum):
    REACHABLE = "reachable"
    AUTH_REQUIRED = "auth_required"
    UNEXPECTED_STATUS = "unexpected_status"
    UNREACHABLE = "unreachable"
    UNKNOWN = "unknown"


class TlsState(StrEnum):
    VALID = "valid"
    EXPIRING = "expiring"
    EXPIRED = "expired"
    INVALID = "invalid"
    UNKNOWN = "unknown"


class ReleaseState(StrEnum):
    UNREAD = "unread"
    NO_UNREAD = "no_unread"
    NO_RELEASES = "no_releases"
    ERROR = "error"
    NOT_CONFIGURED = "not_configured"


class CheckStatus(StrEnum):
    NEVER = "never"
    SUCCESS = "success"
    ERROR = "error"


class EndpointKind(StrEnum):
    INTERNAL = "internal"
    EXTERNAL = "external"
    ADMIN = "admin"


class JobState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL_FAILED = "partial_failed"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


class RefreshKind(StrEnum):
    DOCKER = "docker"
    URL = "url"
    TLS = "tls"
    RELEASES = "releases"
    ALL = "all"


# ---------------------------------------------------------------------------
# 观测视图（先定义：被台账详情引用）
# ---------------------------------------------------------------------------


class ComposeFileView(BaseModel):
    raw: str
    resolved: str | None = None
    # absolute：绝对路径；relative_resolved：相对路径 + 已知绝对 working_dir 已拼接；
    # relative_unknown：相对路径且工作目录未知，位置未确认
    path_state: Literal["absolute", "relative_resolved", "relative_unknown"] = "absolute"


class MountView(BaseModel):
    kind: Literal["bind", "volume", "tmpfs", "other"] = "other"
    source: str = ""
    destination: str = ""
    read_only: bool = False


class PortView(BaseModel):
    host_ip: str = ""
    host_port: int | None = None
    container_port: int | None = None
    protocol: Literal["tcp", "udp"] = "tcp"
    address_family: Literal["ipv4", "ipv6"] = "ipv4"
    network_mode: str = "bridge"
    # published：Docker 报告的主机映射；exposed：仅容器 expose 的内部端口；
    # historical：stopped 容器的配置映射（不算当前占用）；host_network：共享宿主网络未采集
    kind: Literal["published", "exposed", "historical", "host_network"] = "exposed"
    source: Literal["docker", "manual"] = "docker"


class ComponentView(BaseModel):
    source_key: str
    project: str | None = None
    service_name: str | None = None
    container_name: str = ""
    container_id: str = ""
    image_ref: str = ""
    image_id: str = ""
    state: str = "unknown"
    health: HealthState = HealthState.UNKNOWN
    network_mode: str = "bridge"
    ports: list[PortView] = Field(default_factory=list)
    mounts: list[MountView] = Field(default_factory=list)
    compose_working_dir: str | None = None
    compose_files: list[ComposeFileView] = Field(default_factory=list)
    data_paths: list[str] = Field(default_factory=list)
    last_seen_at: str | None = None
    present: bool = True
    required: bool = True
    label: str = ""
    override_source: Literal["docker", "manual"] = "docker"


class CheckView(BaseModel):
    check_kind: str
    check_status: CheckStatus = CheckStatus.NEVER
    current_state: str | None = None
    last_attempt_at: str | None = None
    last_success_at: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    next_due_at: str | None = None
    stale: bool = False
    payload: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# 人工台账
# ---------------------------------------------------------------------------

Name = Annotated[str, Field(min_length=1, max_length=120)]


class ServiceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Name
    description: str = Field(default="", max_length=2000)
    tags: list[str] = Field(default_factory=list, max_length=20)
    notes: str = Field(default="", max_length=4000)

    @field_validator("name")
    @classmethod
    def _strip_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("name must not be blank")
        return cleaned

    @field_validator("tags")
    @classmethod
    def _clean_tags(cls, value: list[str]) -> list[str]:
        return clean_tags(value)


def clean_tags(value: list[str]) -> list[str]:
    """标签清洗：去空白、丢空串、限长 32、去重并按字典序排序。

    排序与 skill-manager 一致：筛选栏把标签按字典序排成一行，
    顺序稳定才不会因为保存动作而跳动。
    """
    seen: set[str] = set()
    for tag in value:
        cleaned = tag.strip()
        if not cleaned:
            continue
        if len(cleaned) > 32:
            raise ValueError("tag too long (max 32)")
        seen.add(cleaned)
    return sorted(seen)


class ServicePatch(BaseModel):
    """PATCH 语义：只更新显式给出的字段，revision 必须匹配现有值。"""

    model_config = ConfigDict(extra="forbid")

    name: Name | None = None
    description: str | None = Field(default=None, max_length=2000)
    tags: list[str] | None = Field(default=None, max_length=20)
    notes: str | None = Field(default=None, max_length=4000)
    revision: int

    @field_validator("name")
    @classmethod
    def _strip_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("name must not be blank")
        return cleaned

    @field_validator("tags")
    @classmethod
    def _clean_tags(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        return clean_tags(value)


class RouteTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    component_source_key: str | None = None
    scheme: Literal["http", "https"] = "http"
    host: str = Field(min_length=1, max_length=255)
    port: int | None = Field(default=None, ge=1, le=65535)
    path_prefix: str = Field(default="", max_length=512)
    note: str = Field(default="", max_length=500)


class EndpointInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(default="", max_length=120)
    kind: EndpointKind = EndpointKind.EXTERNAL
    url: str = Field(min_length=1, max_length=2048)
    probe_url: str | None = Field(default=None, max_length=2048)
    enabled: bool = True
    expected_status_ranges: list[str] = Field(default_factory=list, max_length=10)
    tls_check: bool = True
    route_target: RouteTarget | None = None
    renewal_note: str = Field(default="", max_length=500)


class EndpointRecord(EndpointInput):
    id: str
    service_id: str
    revision: int


class PrimaryEndpointInput(BaseModel):
    """行内改主入口：只收 URL，类型与是否查证书由后端按 URL 判定。"""

    model_config = ConfigDict(extra="forbid")

    url: str = Field(min_length=1, max_length=2048)


class PrimaryEndpointView(BaseModel):
    """列表页要显示的主入口信息（含证书状态）。"""

    id: str
    url: str
    label: str = ""
    kind: EndpointKind = EndpointKind.EXTERNAL
    tls_check: bool = True
    # 证书状态：valid / expiring / expired / invalid / unknown
    tls_state: str = "unknown"
    tls_days_remaining: int | None = None
    tls_not_after: str | None = None
    tls_invalid_reason: str | None = None


class PortNoteInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    host_ip: str = Field(default="", max_length=64)
    host_port: int = Field(ge=1, le=65535)
    container_port: int | None = Field(default=None, ge=1, le=65535)
    protocol: Literal["tcp", "udp"] = "tcp"
    note: str = Field(default="", max_length=500)


class PortNoteRecord(PortNoteInput):
    id: str
    service_id: str
    revision: int


class ReleaseSourceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    owner: str = Field(min_length=1, max_length=100)
    repo: str = Field(min_length=1, max_length=100)
    installed_tag_note: str = Field(default="", max_length=120)


class ReleaseSourceRecord(ReleaseSourceInput):
    id: str
    service_id: str
    revision: int


class ComponentOverrideInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    working_dir: str | None = Field(default=None, max_length=1024)
    config_files: list[str] | None = Field(default=None, max_length=20)
    data_paths: list[str] | None = Field(default=None, max_length=40)
    version_note: str | None = Field(default=None, max_length=500)


class ServiceStatus(BaseModel):
    runtime: RuntimeState = RuntimeState.UNKNOWN
    health: HealthState = HealthState.UNKNOWN
    url: UrlState = UrlState.UNKNOWN
    tls: TlsState = TlsState.UNKNOWN
    release: ReleaseState = ReleaseState.NOT_CONFIGURED
    url_check: CheckView | None = None
    tls_check: CheckView | None = None
    release_check: CheckView | None = None
    unread_releases: int = 0
    primary_url: str | None = None
    component_states: dict[str, str] = Field(default_factory=dict)


class ServiceDetail(BaseModel):
    id: str
    name: str
    description: str
    tags: list[str]
    notes: str
    revision: int
    created_at: str
    updated_at: str
    components: list[ComponentView] = Field(default_factory=list)
    endpoints: list[EndpointRecord] = Field(default_factory=list)
    port_notes: list[PortNoteRecord] = Field(default_factory=list)
    release_source: ReleaseSourceRecord | None = None
    status: ServiceStatus = Field(default_factory=ServiceStatus)


class ServiceListItem(BaseModel):
    id: str
    name: str
    description: str
    tags: list[str]
    revision: int
    updated_at: str
    primary_url: str | None = None
    # 主入口（含证书状态）；没有登记入口时为 None
    primary_endpoint: PrimaryEndpointView | None = None
    component_count: int = 0
    # 该服务包含的 compose 项目（来源信息，不再决定分组）
    projects: list[str] = Field(default_factory=list)
    status: ServiceStatus = Field(default_factory=ServiceStatus)


# ---------------------------------------------------------------------------
# 发现
# ---------------------------------------------------------------------------


class DiscoveryCandidate(BaseModel):
    source_key: str
    project: str | None = None
    service_name: str | None = None
    container_name: str = ""
    container_id: str = ""
    image_ref: str = ""
    state: str = "unknown"
    health: HealthState = HealthState.UNKNOWN
    network_mode: str = "bridge"
    ports: list[PortView] = Field(default_factory=list)
    compose_working_dir: str | None = None
    compose_files: list[ComposeFileView] = Field(default_factory=list)
    ignored: bool = False
    oneoff: bool = False
    bindable: bool = True
    bound_service_id: str | None = None


class DiscoveryImportItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_key: str = Field(min_length=1, max_length=512)
    required: bool = True
    label: str = Field(default="", max_length=120)


class DiscoveryImportRequest(BaseModel):
    """候选导入：service_id 为空则新建业务服务（需 name）。"""

    model_config = ConfigDict(extra="forbid")

    components: list[DiscoveryImportItem] = Field(min_length=1, max_length=100)
    service_id: str | None = None
    name: Name | None = None
    description: str = Field(default="", max_length=2000)
    tags: list[str] = Field(default_factory=list, max_length=20)


class DiscoveryDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_keys: list[str] = Field(min_length=1, max_length=500)
    ignored: bool


# ---------------------------------------------------------------------------
# 资源总览
# ---------------------------------------------------------------------------


class PortOverviewRow(PortView):
    source_key: str | None = None
    container_name: str = ""
    project: str | None = None
    service_id: str | None = None
    service_name: str | None = None
    note: str = ""
    origin: Literal["docker", "manual"] = "docker"


class DomainOverviewRow(BaseModel):
    host: str
    scheme: str
    port: int | None = None
    path: str = ""
    url: str
    endpoint_id: str
    endpoint_label: str
    endpoint_kind: EndpointKind
    service_id: str
    service_name: str
    route_target: RouteTarget | None = None
    tls_state: TlsState = TlsState.UNKNOWN
    tls_days_remaining: int | None = None
    # 证书无效的原因（self_signed 等），页面据此说清「为什么无效」
    tls_invalid_reason: str | None = None
    is_ip: bool = False


class CertificateOverviewRow(BaseModel):
    host: str
    port: int
    tls_state: TlsState = TlsState.UNKNOWN
    subject: str = ""
    issuer: str = ""
    sans: list[str] = Field(default_factory=list)
    not_before: str | None = None
    not_after: str | None = None
    days_remaining: int | None = None
    fingerprint: str = ""
    used_by: list[str] = Field(default_factory=list)
    error: str | None = None
    invalid_reason: str | None = None


# ---------------------------------------------------------------------------
# Release
# ---------------------------------------------------------------------------


class ReleaseView(BaseModel):
    owner: str
    repo: str
    release_id: int
    tag: str
    name: str = ""
    published_at: str | None = None
    body: str = ""
    html_url: str = ""
    read: bool = False


class ReleaseListResponse(BaseModel):
    source: ReleaseSourceRecord | None = None
    items: list[ReleaseView] = Field(default_factory=list)
    check: CheckView | None = None
    truncated: bool = False
    latest_release_id: int | None = None


class ReleaseReadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    release_ids: list[int] = Field(min_length=1, max_length=500)


# ---------------------------------------------------------------------------
# 任务 / 汇总 / 备份 / 会话
# ---------------------------------------------------------------------------


class RefreshRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: RefreshKind
    target_id: str | None = None


class RefreshJobView(BaseModel):
    id: str
    kind: RefreshKind
    target_id: str | None = None
    state: JobState
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
    counts: dict[str, int] = Field(default_factory=dict)
    error: str | None = None
    deduplicated: bool = False


class SummaryResponse(BaseModel):
    services: int = 0
    components: int = 0
    # 容器侧观测计数：发现 vs 已关联 vs 未入账
    docker_components: int = 0
    docker_running: int = 0
    docker_missing: int = 0
    unregistered_components: int = 0
    ignored_components: int = 0
    docker_available: bool = False
    docker_error: str | None = None
    docker_last_success_at: str | None = None
    counts: dict[str, dict[str, int]] = Field(default_factory=dict)
    # 全库标签词表：筛选栏的候选来源（不随搜索结果缩小）
    all_tags: list[str] = Field(default_factory=list)
    unread_releases: int = 0
    registry_revision: int = 0
    checker_heartbeat: str | None = None


class BackupPreviewResponse(BaseModel):
    digest: str
    registry_revision: int
    counts: dict[str, int] = Field(default_factory=dict)
    current_counts: dict[str, int] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class RestoreRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    digest: str
    registry_revision: int
    confirm: bool = False


class SessionResponse(BaseModel):
    authenticated: bool
    expires_at: str | None = None


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    password: str = Field(min_length=1, max_length=512)
