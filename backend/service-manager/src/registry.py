"""人工台账服务（design §3 / §4）。

边界：
- 只写人工表（services / service_components / component_overrides / endpoints /
  port_notes / release_sources / discovery_decisions）。
- 绝不写 docker_components（那是扫描器的事），绝不调用 Docker 写操作。
- 所有 mutation 在同一事务里递增全局 registry_revision；实体 PATCH 同时核对
  实体 revision，避免旧表单覆盖新记录。
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

from src.db import Store
from src.docker_reader import project_from_source_key
from src.errors import bad_request, conflict, not_found
from src.models import (
    ComponentOverrideInput,
    EndpointInput,
    EndpointRecord,
    PortNoteInput,
    PortNoteRecord,
    ReleaseSourceInput,
    ReleaseSourceRecord,
    ServiceCreate,
    ServiceDetail,
    ServiceListItem,
    ServicePatch,
    clean_tags,
)
from src.urls import ParsedUrl, parse_http_url, validate_probe_url

JOURNAL_MODE = "wal"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _new_id() -> str:
    return str(uuid.uuid4())


def _row_to_service(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "description": row["description"],
        "category": row["category"],
        "tags": json.loads(row["tags"] or "[]"),
        "notes": row["notes"],
        "revision": int(row["revision"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def endpoint_row_to_record(row: sqlite3.Row) -> EndpointRecord:
    route = row["route_target"]
    return EndpointRecord(
        id=row["id"],
        service_id=row["service_id"],
        label=row["label"],
        kind=row["kind"],
        url=row["url"],
        probe_url=row["probe_url"],
        enabled=bool(row["enabled"]),
        expected_status_ranges=json.loads(row["expected_status_ranges"] or "[]"),
        tls_check=bool(row["tls_check"]),
        route_target=json.loads(route) if route else None,
        renewal_note=row["renewal_note"],
        revision=int(row["revision"]),
    )


def port_note_row_to_record(row: sqlite3.Row) -> PortNoteRecord:
    return PortNoteRecord(
        id=row["id"],
        service_id=row["service_id"],
        host_ip=row["host_ip"],
        host_port=int(row["host_port"]),
        container_port=row["container_port"],
        protocol=row["protocol"],
        note=row["note"],
        revision=int(row["revision"]),
    )


def release_source_row_to_record(row: sqlite3.Row) -> ReleaseSourceRecord:
    return ReleaseSourceRecord(
        id=row["id"],
        service_id=row["service_id"],
        owner=row["owner"],
        repo=row["repo"],
        installed_tag_note=row["installed_tag_note"],
        revision=int(row["revision"]),
    )


class Registry:
    def __init__(self, store: Store) -> None:
        self.store = store

    # ------------------------------------------------------------------
    # 服务
    # ------------------------------------------------------------------

    def create_service(self, payload: ServiceCreate) -> ServiceDetail:
        now = _now()
        service_id = _new_id()
        with self.store.transaction() as conn:
            conn.execute(
                "INSERT INTO services(id, name, description, category, tags, notes,"
                " revision, created_at, updated_at) VALUES (?,?,?,?,?,?,1,?,?)",
                (
                    service_id,
                    payload.name,
                    payload.description,
                    payload.category,
                    json.dumps(payload.tags, ensure_ascii=False),
                    payload.notes,
                    now,
                    now,
                ),
            )
            Store.bump_registry_revision(conn)
        return self.get_service(service_id)

    def list_services(
        self,
        *,
        query: str = "",
        category: str = "",
        tag: str = "",
        page: int = 1,
        page_size: int = 50,
        only_unhealthy: bool = False,
    ) -> tuple[list[ServiceListItem], int]:
        page = max(1, page)
        page_size = min(100, max(1, page_size))
        clauses: list[str] = []
        params: list[Any] = []
        if query:
            like = f"%{query.lower()}%"
            clauses.append(
                "(lower(s.name) LIKE ? OR lower(s.description) LIKE ? OR "
                "lower(s.category) LIKE ? OR lower(s.tags) LIKE ? OR s.id IN ("
                "SELECT e.service_id FROM endpoints e WHERE lower(e.url) LIKE ?) OR "
                "s.id IN (SELECT c.service_id FROM service_components c WHERE "
                "lower(c.source_key) LIKE ?))"
            )
            params.extend([like] * 6)
        if category:
            clauses.append("s.category = ?")
            params.append(category)
        if tag:
            clauses.append("s.tags LIKE ?")
            params.append(f'%"{tag}"%')
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        with self.store.read() as conn:
            total = int(
                conn.execute(
                    f"SELECT COUNT(*) AS c FROM services s{where}", params
                ).fetchone()["c"]
            )
            rows = conn.execute(
                f"SELECT * FROM services s{where} ORDER BY lower(s.name) "
                f"LIMIT ? OFFSET ?",
                [*params, page_size, (page - 1) * page_size],
            ).fetchall()
            items: list[ServiceListItem] = []
            for row in rows:
                service = _row_to_service(row)
                component_count = int(
                    conn.execute(
                        "SELECT COUNT(*) AS c FROM service_components "
                        "WHERE service_id = ?",
                        (service["id"],),
                    ).fetchone()["c"]
                )
                endpoints = conn.execute(
                    "SELECT * FROM endpoints WHERE service_id = ? "
                    "AND enabled = 1 ORDER BY kind, created_at",
                    (service["id"],),
                ).fetchall()
                primary = None
                for endpoint_row in endpoints:
                    record = endpoint_row_to_record(endpoint_row)
                    if record.kind.value == "external":
                        primary = record.url
                        break
                if primary is None and endpoints:
                    primary = endpoint_row_to_record(endpoints[0]).url
                items.append(
                    ServiceListItem(
                        id=service["id"],
                        name=service["name"],
                        description=service["description"],
                        category=service["category"],
                        tags=service["tags"],
                        revision=service["revision"],
                        updated_at=service["updated_at"],
                        primary_url=primary,
                        component_count=component_count,
                    )
                )
        return items, total

    def get_service(self, service_id: str) -> ServiceDetail:
        with self.store.read() as conn:
            row = conn.execute(
                "SELECT * FROM services WHERE id = ?", (service_id,)
            ).fetchone()
            if row is None:
                raise not_found("服务不存在")
            service = _row_to_service(row)
            endpoints = [
                endpoint_row_to_record(item)
                for item in conn.execute(
                    "SELECT * FROM endpoints WHERE service_id = ? "
                    "ORDER BY kind, created_at",
                    (service_id,),
                ).fetchall()
            ]
            port_notes = [
                port_note_row_to_record(item)
                for item in conn.execute(
                    "SELECT * FROM port_notes WHERE service_id = ? "
                    "ORDER BY host_port",
                    (service_id,),
                ).fetchall()
            ]
            source_row = conn.execute(
                "SELECT * FROM release_sources WHERE service_id = ?", (service_id,)
            ).fetchone()
        return ServiceDetail(
            **service,
            endpoints=endpoints,
            port_notes=port_notes,
            release_source=(
                release_source_row_to_record(source_row) if source_row else None
            ),
        )

    def update_service(self, service_id: str, payload: ServicePatch) -> ServiceDetail:
        with self.store.transaction() as conn:
            row = conn.execute(
                "SELECT * FROM services WHERE id = ?", (service_id,)
            ).fetchone()
            if row is None:
                raise not_found("服务不存在")
            if int(row["revision"]) != payload.revision:
                raise conflict(
                    "记录已被修改，请刷新后重试", code="revision_conflict"
                )
            updates: dict[str, Any] = {}
            if payload.name is not None:
                updates["name"] = payload.name
            if payload.description is not None:
                updates["description"] = payload.description
            if payload.category is not None:
                updates["category"] = payload.category
            if payload.tags is not None:
                updates["tags"] = json.dumps(payload.tags, ensure_ascii=False)
            if payload.notes is not None:
                updates["notes"] = payload.notes
            updates["revision"] = payload.revision + 1
            updates["updated_at"] = _now()
            assignments = ", ".join(f"{key} = ?" for key in updates)
            conn.execute(
                f"UPDATE services SET {assignments} WHERE id = ?",
                [*updates.values(), service_id],
            )
            Store.bump_registry_revision(conn)
        return self.get_service(service_id)

    def delete_service(self, service_id: str) -> dict[str, Any]:
        """只移除台账；运行中的容器完全不受影响（design §4 第 5 条）。"""
        with self.store.transaction() as conn:
            row = conn.execute(
                "SELECT id FROM services WHERE id = ?", (service_id,)
            ).fetchone()
            if row is None:
                raise not_found("服务不存在")
            conn.execute("DELETE FROM services WHERE id = ?", (service_id,))
            Store.bump_registry_revision(conn)
        return {"deleted": service_id}

    # ------------------------------------------------------------------
    # 组件绑定
    # ------------------------------------------------------------------

    def bind_component(
        self,
        conn: sqlite3.Connection,
        service_id: str,
        source_key: str,
        *,
        required: bool = True,
        label: str = "",
    ) -> str:
        existing = conn.execute(
            "SELECT service_id FROM service_components WHERE source_key = ?",
            (source_key,),
        ).fetchone()
        if existing is not None:
            if existing["service_id"] == service_id:
                raise conflict(
                    "该组件已属于当前服务", code="duplicate_binding"
                )
            raise conflict(
                "该组件已被其他服务绑定", code="duplicate_binding"
            )
        conn.execute(
            "INSERT INTO service_components(id, service_id, source_key, required,"
            " label, created_at) VALUES (?,?,?,?,?,?)",
            (
                _new_id(),
                service_id,
                source_key,
                1 if required else 0,
                label,
                _now(),
            ),
        )
        return source_key

    def unbind_component(self, service_id: str, source_key: str) -> None:
        with self.store.transaction() as conn:
            cur = conn.execute(
                "DELETE FROM service_components WHERE service_id = ? "
                "AND source_key = ?",
                (service_id, source_key),
            )
            if cur.rowcount == 0:
                raise not_found("组件未绑定到该服务")
            Store.bump_registry_revision(conn)

    def set_component_required(
        self, service_id: str, source_key: str, required: bool, label: str | None = None
    ) -> None:
        with self.store.transaction() as conn:
            fields = ["required = ?"]
            params: list[Any] = [1 if required else 0]
            if label is not None:
                fields.append("label = ?")
                params.append(label)
            params.extend([service_id, source_key])
            cur = conn.execute(
                f"UPDATE service_components SET {', '.join(fields)} "
                "WHERE service_id = ? AND source_key = ?",
                params,
            )
            if cur.rowcount == 0:
                raise not_found("组件未绑定到该服务")
            Store.bump_registry_revision(conn)

    def list_bindings(self, service_id: str) -> list[dict[str, Any]]:
        with self.store.read() as conn:
            rows = conn.execute(
                "SELECT * FROM service_components WHERE service_id = ? "
                "ORDER BY created_at",
                (service_id,),
            ).fetchall()
        return [
            {
                "source_key": row["source_key"],
                "required": bool(row["required"]),
                "label": row["label"],
            }
            for row in rows
        ]

    def binding_map(self) -> dict[str, tuple[str, bool, str]]:
        """source_key → (service_id, required, label)。"""
        with self.store.read() as conn:
            rows = conn.execute(
                "SELECT source_key, service_id, required, label FROM service_components"
            ).fetchall()
        return {
            row["source_key"]: (
                row["service_id"],
                bool(row["required"]),
                row["label"] or "",
            )
            for row in rows
        }

    def projects_by_service(self) -> dict[str, list[str]]:
        """service_id → 它包含的 compose 项目（按绑定顺序去重）。

        只读台账里的 source_key，不额外问 Docker；没有 compose 标签的
        游离容器（nas:container:*）不计入任何项目。
        """
        with self.store.read() as conn:
            rows = conn.execute(
                "SELECT service_id, source_key FROM service_components "
                "ORDER BY created_at"
            ).fetchall()
        result: dict[str, list[str]] = {}
        for row in rows:
            project = project_from_source_key(row["source_key"])
            if not project:
                continue
            bucket = result.setdefault(row["service_id"], [])
            if project not in bucket:
                bucket.append(project)
        return result

    # ------------------------------------------------------------------
    # 部署信息覆盖
    # ------------------------------------------------------------------

    def set_override(self, source_key: str, payload: ComponentOverrideInput) -> None:
        with self.store.transaction() as conn:
            conn.execute(
                "INSERT INTO component_overrides(source_key, working_dir, config_files,"
                " data_paths, version_note, updated_at) VALUES (?,?,?,?,?,?) "
                "ON CONFLICT(source_key) DO UPDATE SET working_dir = excluded.working_dir,"
                " config_files = excluded.config_files, data_paths = excluded.data_paths,"
                " version_note = excluded.version_note, updated_at = excluded.updated_at",
                (
                    source_key,
                    payload.working_dir,
                    json.dumps(payload.config_files, ensure_ascii=False)
                    if payload.config_files is not None
                    else None,
                    json.dumps(payload.data_paths, ensure_ascii=False)
                    if payload.data_paths is not None
                    else None,
                    payload.version_note,
                    _now(),
                ),
            )
            Store.bump_registry_revision(conn)

    def override_map(self) -> dict[str, dict[str, Any]]:
        with self.store.read() as conn:
            rows = conn.execute("SELECT * FROM component_overrides").fetchall()
        result: dict[str, dict[str, Any]] = {}
        for row in rows:
            result[row["source_key"]] = {
                "working_dir": row["working_dir"],
                "config_files": json.loads(row["config_files"])
                if row["config_files"]
                else None,
                "data_paths": json.loads(row["data_paths"])
                if row["data_paths"]
                else None,
                "version_note": row["version_note"],
            }
        return result

    # ------------------------------------------------------------------
    # 入口
    # ------------------------------------------------------------------

    def _validated_endpoint(self, payload: EndpointInput) -> tuple[EndpointInput, ParsedUrl]:
        parsed = parse_http_url(payload.url, field="url")
        if payload.probe_url:
            validate_probe_url(payload.probe_url, field="probe_url")
        for item in payload.expected_status_ranges:
            parse_status_range(item)
        return payload, parsed

    def add_endpoint(self, service_id: str, payload: EndpointInput) -> EndpointRecord:
        payload, _parsed = self._validated_endpoint(payload)
        now = _now()
        endpoint_id = _new_id()
        with self.store.transaction() as conn:
            self._require_service(conn, service_id)
            conn.execute(
                "INSERT INTO endpoints(id, service_id, label, kind, url, probe_url,"
                " enabled, expected_status_ranges, tls_check, route_target,"
                " renewal_note, revision, created_at, updated_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,1,?,?)",
                (
                    endpoint_id,
                    service_id,
                    payload.label,
                    payload.kind.value,
                    payload.url,
                    payload.probe_url,
                    1 if payload.enabled else 0,
                    json.dumps(payload.expected_status_ranges),
                    1 if payload.tls_check else 0,
                    payload.route_target.model_dump_json()
                    if payload.route_target
                    else None,
                    payload.renewal_note,
                    now,
                    now,
                ),
            )
            Store.bump_registry_revision(conn)
            row = conn.execute(
                "SELECT * FROM endpoints WHERE id = ?", (endpoint_id,)
            ).fetchone()
        return endpoint_row_to_record(row)

    def update_endpoint(
        self, service_id: str, endpoint_id: str, payload: EndpointInput
    ) -> EndpointRecord:
        payload, _parsed = self._validated_endpoint(payload)
        with self.store.transaction() as conn:
            row = conn.execute(
                "SELECT * FROM endpoints WHERE id = ? AND service_id = ?",
                (endpoint_id, service_id),
            ).fetchone()
            if row is None:
                raise not_found("入口不存在")
            conn.execute(
                "UPDATE endpoints SET label = ?, kind = ?, url = ?, probe_url = ?,"
                " enabled = ?, expected_status_ranges = ?, tls_check = ?,"
                " route_target = ?, renewal_note = ?, revision = ?, updated_at = ?"
                " WHERE id = ?",
                (
                    payload.label,
                    payload.kind.value,
                    payload.url,
                    payload.probe_url,
                    1 if payload.enabled else 0,
                    json.dumps(payload.expected_status_ranges),
                    1 if payload.tls_check else 0,
                    payload.route_target.model_dump_json()
                    if payload.route_target
                    else None,
                    payload.renewal_note,
                    int(row["revision"]) + 1,
                    _now(),
                    endpoint_id,
                ),
            )
            Store.bump_registry_revision(conn)
            updated = conn.execute(
                "SELECT * FROM endpoints WHERE id = ?", (endpoint_id,)
            ).fetchone()
        return endpoint_row_to_record(updated)

    def delete_endpoint(self, service_id: str, endpoint_id: str) -> None:
        with self.store.transaction() as conn:
            cur = conn.execute(
                "DELETE FROM endpoints WHERE id = ? AND service_id = ?",
                (endpoint_id, service_id),
            )
            if cur.rowcount == 0:
                raise not_found("入口不存在")
            Store.bump_registry_revision(conn)

    def list_endpoints(self, *, only_enabled: bool = False) -> list[EndpointRecord]:
        sql = "SELECT * FROM endpoints"
        if only_enabled:
            sql += " WHERE enabled = 1"
        sql += " ORDER BY service_id, kind, created_at"
        with self.store.read() as conn:
            rows = conn.execute(sql).fetchall()
        return [endpoint_row_to_record(row) for row in rows]

    # ------------------------------------------------------------------
    # 手工端口
    # ------------------------------------------------------------------

    def add_port_note(self, service_id: str, payload: PortNoteInput) -> PortNoteRecord:
        now = _now()
        note_id = _new_id()
        with self.store.transaction() as conn:
            self._require_service(conn, service_id)
            conn.execute(
                "INSERT INTO port_notes(id, service_id, host_ip, host_port,"
                " container_port, protocol, note, revision, created_at, updated_at)"
                " VALUES (?,?,?,?,?,?,?,1,?,?)",
                (
                    note_id,
                    service_id,
                    payload.host_ip,
                    payload.host_port,
                    payload.container_port,
                    payload.protocol,
                    payload.note,
                    now,
                    now,
                ),
            )
            Store.bump_registry_revision(conn)
            row = conn.execute(
                "SELECT * FROM port_notes WHERE id = ?", (note_id,)
            ).fetchone()
        return port_note_row_to_record(row)

    def delete_port_note(self, service_id: str, note_id: str) -> None:
        with self.store.transaction() as conn:
            cur = conn.execute(
                "DELETE FROM port_notes WHERE id = ? AND service_id = ?",
                (note_id, service_id),
            )
            if cur.rowcount == 0:
                raise not_found("端口记录不存在")
            Store.bump_registry_revision(conn)

    def list_port_notes(self) -> list[PortNoteRecord]:
        with self.store.read() as conn:
            rows = conn.execute("SELECT * FROM port_notes").fetchall()
        return [port_note_row_to_record(row) for row in rows]

    # ------------------------------------------------------------------
    # GitHub 仓库关联
    # ------------------------------------------------------------------

    def set_release_source(
        self, service_id: str, payload: ReleaseSourceInput
    ) -> ReleaseSourceRecord:
        owner = payload.owner.strip()
        repo = payload.repo.strip()
        if not owner or not repo:
            raise bad_request("owner/repo 不能为空")
        now = _now()
        with self.store.transaction() as conn:
            self._require_service(conn, service_id)
            row = conn.execute(
                "SELECT * FROM release_sources WHERE service_id = ?", (service_id,)
            ).fetchone()
            if row is None:
                source_id = _new_id()
                conn.execute(
                    "INSERT INTO release_sources(id, service_id, owner, repo,"
                    " installed_tag_note, revision, created_at, updated_at)"
                    " VALUES (?,?,?,?,?,1,?,?)",
                    (source_id, service_id, owner, repo, payload.installed_tag_note, now, now),
                )
            else:
                source_id = row["id"]
                conn.execute(
                    "UPDATE release_sources SET owner = ?, repo = ?,"
                    " installed_tag_note = ?, revision = ?, updated_at = ?"
                    " WHERE id = ?",
                    (
                        owner,
                        repo,
                        payload.installed_tag_note,
                        int(row["revision"]) + 1,
                        now,
                        source_id,
                    ),
                )
            Store.bump_registry_revision(conn)
            updated = conn.execute(
                "SELECT * FROM release_sources WHERE id = ?", (source_id,)
            ).fetchone()
        return release_source_row_to_record(updated)

    def delete_release_source(self, service_id: str) -> None:
        with self.store.transaction() as conn:
            cur = conn.execute(
                "DELETE FROM release_sources WHERE service_id = ?", (service_id,)
            )
            if cur.rowcount == 0:
                raise not_found("该服务未关联 GitHub 仓库")
            Store.bump_registry_revision(conn)

    def list_release_sources(self) -> list[ReleaseSourceRecord]:
        with self.store.read() as conn:
            rows = conn.execute("SELECT * FROM release_sources").fetchall()
        return [release_source_row_to_record(row) for row in rows]

    def get_release_source_for_service(
        self, service_id: str
    ) -> ReleaseSourceRecord | None:
        with self.store.read() as conn:
            row = conn.execute(
                "SELECT * FROM release_sources WHERE service_id = ?", (service_id,)
            ).fetchone()
        return release_source_row_to_record(row) if row else None

    # ------------------------------------------------------------------
    # 忽略决定
    # ------------------------------------------------------------------

    def set_ignored(self, source_keys: list[str], ignored: bool) -> int:
        now = _now()
        with self.store.transaction() as conn:
            for source_key in source_keys:
                conn.execute(
                    "INSERT INTO discovery_decisions(source_key, ignored, updated_at)"
                    " VALUES (?,?,?) ON CONFLICT(source_key) DO UPDATE SET"
                    " ignored = excluded.ignored, updated_at = excluded.updated_at",
                    (source_key, 1 if ignored else 0, now),
                )
            Store.bump_registry_revision(conn)
        return self.store.registry_revision

    def ignored_keys(self) -> set[str]:
        with self.store.read() as conn:
            rows = conn.execute(
                "SELECT source_key FROM discovery_decisions WHERE ignored = 1"
            ).fetchall()
        return {row["source_key"] for row in rows}

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    @staticmethod
    def _require_service(conn: sqlite3.Connection, service_id: str) -> sqlite3.Row:
        row = conn.execute(
            "SELECT * FROM services WHERE id = ?", (service_id,)
        ).fetchone()
        if row is None:
            raise not_found("服务不存在")
        return row


def parse_status_range(value: str) -> tuple[int, int]:
    """`200` / `200-399` → (low, high)。"""
    text = value.strip()
    if "-" in text:
        low_text, high_text = text.split("-", 1)
        try:
            low, high = int(low_text), int(high_text)
        except ValueError as exc:
            raise bad_request(
                "期望状态码范围格式应为 200 或 200-399",
                {"expected_status_ranges": "格式应为 200 或 200-399"},
            ) from exc
    else:
        try:
            low = high = int(text)
        except ValueError as exc:
            raise bad_request(
                "期望状态码范围格式应为 200 或 200-399",
                {"expected_status_ranges": "格式应为 200 或 200-399"},
            ) from exc
    if not (100 <= low <= high <= 599):
        raise bad_request(
            "期望状态码范围必须在 100-599 且低值不大于高值",
            {"expected_status_ranges": "范围必须在 100-599"},
        )
    return low, high
