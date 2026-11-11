"""服务状态投影（design §6 通用状态 / 各维度枚举）。

- runtime running/partial/stopped/missing/unknown
  required 组件全在跑 = running；部分 = partial；全停 = stopped；
  存在 missing = missing；未绑定组件 = unknown
- health：Docker health 未配置 → not_configured（不能写「健康」）
- URL / TLS / Release 读 check_results 的 current_state
- 首屏可聚合异常计数，但不抹平维度
"""

from __future__ import annotations

from typing import Any

from src.checks.common import CheckStore
from src.checks.github import ReleaseStore
from src.discovery import DiscoveryService
from src.models import (
    CheckStatus,
    CheckView,
    ComponentView,
    HealthState,
    ReleaseState,
    RuntimeState,
    ServiceStatus,
    TlsState,
    UrlState,
)
from src.registry import Registry


def compute_runtime(
    *, components: list[ComponentView], bound: bool
) -> RuntimeState:
    if not bound or not components:
        return RuntimeState.UNKNOWN
    required = [item for item in components if item.required]
    pool = required or components
    states = [item.state for item in pool]
    if any(state == "missing" for state in states):
        return RuntimeState.MISSING
    running = [state for state in states if state == "running"]
    if len(running) == len(states):
        return RuntimeState.RUNNING
    if running:
        return RuntimeState.PARTIAL
    return RuntimeState.STOPPED


def compute_health(*, components: list[ComponentView], bound: bool) -> HealthState:
    """一个服务多个组件时的聚合健康。

    优先级：unhealthy > starting > unknown > not_configured > healthy。
    只要有一个组件没有配置健康检查，聚合结果就不许写「健康」——否则
    「前端没配检查、后端报 healthy」会被误读成整个服务健康。
    """
    if not bound or not components:
        return HealthState.UNKNOWN
    required = [item for item in components if item.required] or components
    values = [item.health for item in required]
    for priority in (
        HealthState.UNHEALTHY,
        HealthState.STARTING,
        HealthState.UNKNOWN,
        HealthState.NOT_CONFIGURED,
    ):
        if priority in values:
            return priority
    return HealthState.HEALTHY


def check_state(check: CheckView | None, *, fallback: str) -> str:
    """失败时 current_state 仍是该维度的失败值（不是旧绿色）。"""
    if check is None:
        return fallback
    if check.current_state:
        return check.current_state
    return fallback


class StatusProjector:
    def __init__(
        self,
        registry: Registry,
        discovery: DiscoveryService,
        releases: ReleaseStore | None = None,
    ) -> None:
        self.registry = registry
        self.discovery = discovery
        self.checks = CheckStore(registry.store)
        self.releases = releases

    def components_for(self, service_id: str) -> list[ComponentView]:
        bound = self.registry.list_bindings(service_id)
        observed = self.discovery.components()
        overrides = self.registry.override_map()
        views: list[ComponentView] = []
        for item in bound:
            source_key = item["source_key"]
            component = observed.get(source_key)
            override = overrides.get(source_key) or {}
            if component is None:
                views.append(
                    ComponentView(
                        source_key=source_key,
                        container_name="",
                        state="missing",
                        health=HealthState.UNKNOWN,
                        present=False,
                        required=item["required"],
                        label=item["label"],
                        compose_working_dir=override.get("working_dir"),
                        data_paths=override.get("data_paths") or [],
                        override_source="manual" if override.get("working_dir") else "docker",
                    )
                )
                continue
            view = self._component_view(
                component, required=item["required"], label=item["label"], override=override
            )
            views.append(view)
        return views

    def _component_view(
        self,
        component: dict[str, Any],
        *,
        required: bool,
        label: str,
        override: dict[str, Any] | None = None,
    ) -> ComponentView:
        from src.models import ComposeFileView, MountView, PortView

        override = override or {}
        working_dir = override.get("working_dir") or component.get("compose_working_dir")
        raw_config_files = override.get("config_files")
        if raw_config_files:
            files = [
                ComposeFileView(
                    raw=item,
                    resolved=item
                    if item.startswith("/")
                    else (f"{working_dir.rstrip('/')}/{item}" if working_dir else None),
                    path_state="absolute"
                    if item.startswith("/")
                    else ("relative_resolved" if working_dir else "relative_unknown"),
                )
                for item in raw_config_files
            ]
        else:
            files = [ComposeFileView(**item) for item in component.get("compose_files", [])]
            if not override.get("working_dir") and working_dir:
                pass
        data_paths = override.get("data_paths") or [
            mount["destination"] for mount in component.get("mounts", [])
        ]
        return ComponentView(
            source_key=component["source_key"],
            project=component.get("project"),
            service_name=component.get("service_name"),
            container_name=component.get("container_name", ""),
            container_id=component.get("container_id", ""),
            image_ref=component.get("image_ref", ""),
            image_id=component.get("image_id", ""),
            state=component.get("state", "unknown"),
            health=HealthState(component.get("health", "unknown")),
            network_mode=component.get("network_mode", "bridge"),
            ports=[PortView(**item) for item in component.get("ports", [])],
            mounts=[MountView(**item) for item in component.get("mounts", [])],
            compose_working_dir=working_dir,
            compose_files=files,
            data_paths=data_paths,
            last_seen_at=component.get("last_seen_at"),
            present=component.get("state") != "missing",
            required=required,
            label=label,
            override_source="manual" if override else "docker",
        )

    def status_for(self, service_id: str, *, components: list[ComponentView] | None = None) -> ServiceStatus:
        views = components if components is not None else self.components_for(service_id)
        bound = bool(views)
        endpoints = [
            item
            for item in self.registry.list_endpoints(only_enabled=True)
            if item.service_id == service_id
        ]
        url_check: CheckView | None = None
        tls_check: CheckView | None = None
        for endpoint in endpoints:
            if url_check is None:
                url_check = self.checks.get(
                    target_type="endpoint", target_id=endpoint.id, check_kind="url"
                )
            if tls_check is None and endpoint.tls_check and endpoint.url.startswith("https"):
                tls_check = self.checks.get(
                    target_type="endpoint", target_id=endpoint.id, check_kind="tls"
                )
        release_source = self.registry.get_release_source_for_service(service_id)
        release_check: CheckView | None = None
        unread = 0
        if release_source is not None:
            release_check = self.checks.get(
                target_type="service", target_id=service_id, check_kind="releases"
            )
            if self.releases is not None:
                unread = self.releases.unread_count(
                    release_source.id, release_source.owner, release_source.repo
                )
        if release_source is None:
            release_state = ReleaseState.NOT_CONFIGURED
        elif release_check is not None and release_check.check_status == CheckStatus.ERROR:
            release_state = ReleaseState.ERROR
        elif unread > 0:
            release_state = ReleaseState.UNREAD
        elif release_check is not None and release_check.current_state:
            try:
                release_state = ReleaseState(release_check.current_state)
            except ValueError:
                release_state = ReleaseState.NO_UNREAD
        else:
            release_state = ReleaseState.NO_UNREAD

        primary_url = None
        for endpoint in endpoints:
            if endpoint.kind.value == "external":
                primary_url = endpoint.url
                break
        if primary_url is None and endpoints:
            primary_url = endpoints[0].url

        return ServiceStatus(
            runtime=compute_runtime(components=views, bound=bound),
            health=compute_health(components=views, bound=bound),
            url=_enum_or(UrlState, check_state(url_check, fallback="unknown"), UrlState.UNKNOWN),
            tls=_enum_or(TlsState, check_state(tls_check, fallback="unknown"), TlsState.UNKNOWN),
            release=release_state,
            url_check=url_check,
            tls_check=tls_check,
            release_check=release_check,
            unread_releases=unread,
            primary_url=primary_url,
            component_states={item.source_key: item.state for item in views},
        )

    def summary(self) -> dict[str, Any]:
        with self.registry.store.read() as conn:
            services = conn.execute("SELECT id FROM services").fetchall()
            components = conn.execute(
                "SELECT COUNT(*) AS c FROM service_components"
            ).fetchone()["c"]
        counts = {
            "runtime": {item.value: 0 for item in RuntimeState},
            "health": {item.value: 0 for item in HealthState},
            "url": {item.value: 0 for item in UrlState},
            "tls": {item.value: 0 for item in TlsState},
            "release": {item.value: 0 for item in ReleaseState},
        }
        unread_total = 0
        for row in services:
            status = self.status_for(row["id"])
            counts["runtime"][status.runtime.value] += 1
            counts["health"][status.health.value] += 1
            counts["url"][status.url.value] += 1
            counts["tls"][status.tls.value] += 1
            counts["release"][status.release.value] += 1
            unread_total += status.unread_releases
        available, error = self.discovery.scan_available()
        return {
            "services": len(services),
            "components": int(components),
            "docker_available": available,
            "docker_error": error,
            "docker_last_success_at": self.discovery.last_success_at(),
            "counts": counts,
            "unread_releases": unread_total,
            "checker_heartbeat": self.registry.store.get_state("checker_heartbeat"),
            "registry_revision": self.registry.store.registry_revision,
        }


def _enum_or(enum_type, value: str, default):
    try:
        return enum_type(value)
    except ValueError:
        return default
