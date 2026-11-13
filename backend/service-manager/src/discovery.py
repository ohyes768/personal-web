"""Docker 发现（design §3 组件身份 / §4 导入流程）。

- 完整扫描成功才整体替换 docker_components 并递增 scan generation
- 扫描失败保留旧观测，只记录错误
- 已登记组件在成功全量扫描中未出现 → present=false（missing）
- 候选与绑定/忽略决定合并输出
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from src.db import Store
from src.docker_reader import (
    ContainerReader,
    DockerUnavailable,
    ScanResult,
    project_from_source_key,
    scan,
)
from src.errors import conflict
from src.models import (
    ComposeFileView,
    DiscoveryCandidate,
    DiscoveryImportItem,
    DiscoveryImportRequest,
    HealthState,
    MountView,
    PortView,
)
from src.registry import Registry, default_ownership

DOCKER_CHECK_KIND = "docker_scan"


@dataclass
class ScanSnapshot:
    scan_id: int
    finished_at: str
    components: list[dict[str, Any]]
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


class DiscoveryService:
    def __init__(self, store: Store, registry: Registry, reader: ContainerReader | None) -> None:
        self.store = store
        self.registry = registry
        self.reader = reader
        self.last_error: str | None = None
        self._last_success_at: str | None = None

    # -- 扫描 ------------------------------------------------------------

    def run_scan(self, *, now: datetime | None = None) -> ScanSnapshot:
        if self.reader is None:
            self.last_error = "Docker 未配置（SERVICE_MANAGER_DOCKER_HOST 为空）"
            self._record_error(self.last_error)
            return ScanSnapshot(scan_id=0, finished_at="", components=[], error=self.last_error)
        scan_id = self._current_scan_id() + 1
        try:
            result: ScanResult = scan(self.reader, scan_id=scan_id, now=now)
        except DockerUnavailable as exc:
            self.last_error = str(exc)
            self._record_error(self.last_error)
            return ScanSnapshot(scan_id=0, finished_at="", components=[], error=self.last_error)
        except Exception as exc:  # noqa: BLE001 - 采集失败一律不发布快照
            self.last_error = f"扫描失败: {exc}"
            self._record_error(self.last_error)
            return ScanSnapshot(scan_id=0, finished_at="", components=[], error=self.last_error)

        self._publish(result)
        self.last_error = None
        self._last_success_at = result.finished_at
        return ScanSnapshot(
            scan_id=result.scan_id,
            finished_at=result.finished_at,
            components=result.components,
        )

    def _current_scan_id(self) -> int:
        value = self.store.get_state("docker_scan_generation")
        try:
            return int(value or 0)
        except ValueError:
            return 0

    def _record_error(self, message: str) -> None:
        with self.store.transaction() as conn:
            Store._set_state(conn, "docker_last_error", message)
            Store._set_state(
                conn,
                "docker_last_attempt_at",
                datetime.now(timezone.utc).isoformat(timespec="seconds"),
            )

    def _publish(self, result: ScanResult) -> None:
        """单事务替换观测表；只删本轮未出现的，保留人工覆盖表。"""
        seen = {item["source_key"] for item in result.components}
        with self.store.transaction() as conn:
            for item in result.components:
                conn.execute(
                    "INSERT INTO docker_components(source_key, project, service_name,"
                    " container_id, container_name, image_ref, image_id, state, health,"
                    " network_mode, ports, mounts, compose_working_dir, compose_files,"
                    " oneoff, last_seen_at, scan_id)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
                    " ON CONFLICT(source_key) DO UPDATE SET"
                    " project = excluded.project, service_name = excluded.service_name,"
                    " container_id = excluded.container_id,"
                    " container_name = excluded.container_name,"
                    " image_ref = excluded.image_ref, image_id = excluded.image_id,"
                    " state = excluded.state, health = excluded.health,"
                    " network_mode = excluded.network_mode, ports = excluded.ports,"
                    " mounts = excluded.mounts,"
                    " compose_working_dir = excluded.compose_working_dir,"
                    " compose_files = excluded.compose_files,"
                    " oneoff = excluded.oneoff, last_seen_at = excluded.last_seen_at,"
                    " scan_id = excluded.scan_id",
                    (
                        item["source_key"],
                        item["project"],
                        item["service_name"],
                        item["container_id"],
                        item["container_name"],
                        item["image_ref"],
                        item["image_id"],
                        item["state"],
                        item["health"],
                        item["network_mode"],
                        json.dumps(item["ports"], ensure_ascii=False),
                        json.dumps(item["mounts"], ensure_ascii=False),
                        item["compose_working_dir"],
                        json.dumps(item["compose_files"], ensure_ascii=False),
                        1 if item["oneoff"] else 0,
                        result.finished_at,
                        result.scan_id,
                    ),
                )
            # 本轮成功扫描中未出现的组件：保留台账，标 missing（design §3）
            placeholders = ",".join("?" for _ in seen) or "''"
            conn.execute(
                f"UPDATE docker_components SET state = 'missing', scan_id = ? "
                f"WHERE source_key NOT IN ({placeholders})",
                [result.scan_id, *seen],
            )
            Store._set_state(conn, "docker_scan_generation", str(result.scan_id))
            Store._set_state(conn, "docker_last_success_at", result.finished_at)
            Store._set_state(conn, "docker_last_error", "")

    # -- 观测读取 --------------------------------------------------------

    def components(self) -> dict[str, dict[str, Any]]:
        with self.store.read() as conn:
            rows = conn.execute("SELECT * FROM docker_components").fetchall()
        return {row["source_key"]: _component_row(row) for row in rows}

    def component(self, source_key: str) -> dict[str, Any] | None:
        return self.components().get(source_key)

    def scan_available(self) -> tuple[bool, str | None]:
        error = self.store.get_state("docker_last_error") or ""
        last_success = self.store.get_state("docker_last_success_at")
        if self.reader is None:
            return False, "Docker 未配置"
        if error:
            return last_success is not None, error
        return True, None

    def last_success_at(self) -> str | None:
        return self.store.get_state("docker_last_success_at") or self._last_success_at

    # -- 候选 ------------------------------------------------------------

    def candidates(
        self,
        *,
        project: str = "",
        state: str = "",
        ignored: bool | None = None,
        include_ephemeral: bool = False,
    ) -> list[DiscoveryCandidate]:
        components = self.components()
        bindings = self.registry.binding_map()
        ignored_keys = self.registry.ignored_keys()
        rows: list[DiscoveryCandidate] = []
        for source_key, item in components.items():
            is_ignored = source_key in ignored_keys
            if ignored is not None and is_ignored != ignored:
                continue
            if project and item.get("project") != project:
                continue
            if state and item.get("state") != state:
                continue
            ephemeral = bool(item.get("oneoff")) or (
                item.get("state") in ("exited", "dead") and not item.get("project")
            )
            if ephemeral and not include_ephemeral:
                continue
            bound = bindings.get(source_key)
            rows.append(
                DiscoveryCandidate(
                    source_key=source_key,
                    project=item.get("project"),
                    service_name=item.get("service_name"),
                    container_name=item.get("container_name", ""),
                    container_id=item.get("container_id", ""),
                    image_ref=item.get("image_ref", ""),
                    state=item.get("state", "unknown"),
                    health=HealthState(item.get("health", "unknown")),
                    network_mode=item.get("network_mode", "bridge"),
                    ports=[PortView(**port) for port in item.get("ports", [])],
                    compose_working_dir=item.get("compose_working_dir"),
                    compose_files=[
                        ComposeFileView(**entry)
                        for entry in item.get("compose_files", [])
                    ],
                    ignored=is_ignored,
                    oneoff=bool(item.get("oneoff")),
                    bindable=bound is None and not bool(item.get("oneoff")),
                    bound_service_id=bound[0] if bound else None,
                )
            )
        rows.sort(
            key=lambda row: (
                row.project or "~",
                row.service_name or "",
                row.container_name,
            )
        )
        return rows

    # -- 导入 ------------------------------------------------------------

    def import_components(
        self, payload: DiscoveryImportRequest, own_projects: tuple[str, ...] = ()
    ) -> dict[str, Any]:
        components = self.components()
        for item in payload.components:
            observed = components.get(item.source_key)
            if observed is None:
                raise conflict(
                    f"候选组件已不存在：{item.source_key}", code="candidate_missing"
                )
            if observed.get("oneoff"):
                raise conflict(
                    f"一次性任务容器不能导入：{item.source_key}",
                    code="candidate_ephemeral",
                )
        with self.store.transaction() as conn:
            created = False
            service_id = payload.service_id
            if service_id:
                exists = conn.execute(
                    "SELECT id FROM services WHERE id = ?", (service_id,)
                ).fetchone()
                if exists is None:
                    raise conflict("目标服务不存在", code="service_missing")
            else:
                name = (payload.name or "").strip()
                if not name:
                    from src.errors import bad_request

                    raise bad_request(
                        "新建服务需要名称", {"name": "新建服务需要名称"}
                    )
                import uuid

                now = datetime.now(timezone.utc).isoformat(timespec="seconds")
                service_id = str(uuid.uuid4())
                # 默认归属：按这批组件的 compose 项目判定（之后页面上可逐条改）
                projects = [
                    project
                    for project in (
                        project_from_source_key(item.source_key)
                        for item in payload.components
                    )
                    if project
                ]
                ownership = default_ownership(
                    len(payload.components), projects, own_projects
                )
                conn.execute(
                    "INSERT INTO services(id, name, description, category, tags, notes,"
                    " ownership, revision, created_at, updated_at)"
                    " VALUES (?,?,?,?,?,?,?,1,?,?)",
                    (
                        service_id,
                        name,
                        payload.description,
                        payload.category,
                        json.dumps(payload.tags, ensure_ascii=False),
                        "",
                        ownership.value,
                        now,
                        now,
                    ),
                )
                created = True
            bound: list[str] = []
            for item in payload.components:
                self.registry.bind_component(
                    conn,
                    service_id,
                    item.source_key,
                    required=item.required,
                    label=item.label,
                )
                bound.append(item.source_key)
            Store.bump_registry_revision(conn)
        return {
            "service_id": service_id,
            "created": created,
            "bound": bound,
        }


def _component_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "source_key": row["source_key"],
        "project": row["project"],
        "service_name": row["service_name"],
        "container_id": row["container_id"],
        "container_name": row["container_name"],
        "image_ref": row["image_ref"],
        "image_id": row["image_id"],
        "state": row["state"],
        "health": row["health"],
        "network_mode": row["network_mode"],
        "ports": json.loads(row["ports"] or "[]"),
        "mounts": [MountView(**item).model_dump() for item in json.loads(row["mounts"] or "[]")],
        "compose_working_dir": row["compose_working_dir"],
        "compose_files": json.loads(row["compose_files"] or "[]"),
        "oneoff": bool(row["oneoff"]),
        "last_seen_at": row["last_seen_at"],
        "scan_id": row["scan_id"],
    }


def project_is_ephemeral(item: dict[str, Any]) -> bool:
    if item.get("oneoff"):
        return True
    return item.get("state") in ("exited", "dead") and not item.get("project")
