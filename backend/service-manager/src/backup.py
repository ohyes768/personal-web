"""人工台账导出与恢复（design §7 / A12）。

导出：只含人工实体与候选忽略决定。
  - 排除运行快照、历史 job、release 缓存/已读标记、密码/Token/session
  - schema_version=1

恢复：
  1. `/preview` 校验并返回 digest + registry_revision + 数量差异
  2. `/restore` 要求同一 digest + 同一 revision + confirm=true
  3. 恢复前先用 SQLite backup API 生成本地快照
  4. 单事务替换人工表、清关联缓存/检查结果、提升 revision
  5. 失败整笔回滚；恢复不触发外部检查
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from src.db import Store
from src.docker_reader import project_from_source_key
from src.errors import bad_request, conflict
from src.models import Ownership
from src.registry import default_ownership

SCHEMA_VERSION = 1
MAX_BYTES = 5 * 1024 * 1024
MAX_SERVICES = 1000
MAX_ENDPOINTS = 5000

MANUAL_TABLES = (
    "services",
    "service_components",
    "component_overrides",
    "endpoints",
    "port_notes",
    "release_sources",
    "discovery_decisions",
)


class BackupError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def digest_of(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def export_payload(store: Store) -> dict[str, Any]:
    with store.read() as conn:
        services = [dict(row) for row in conn.execute("SELECT * FROM services").fetchall()]
        components = [
            dict(row)
            for row in conn.execute("SELECT * FROM service_components").fetchall()
        ]
        overrides = [
            dict(row)
            for row in conn.execute("SELECT * FROM component_overrides").fetchall()
        ]
        endpoints = [
            dict(row) for row in conn.execute("SELECT * FROM endpoints").fetchall()
        ]
        port_notes = [
            dict(row) for row in conn.execute("SELECT * FROM port_notes").fetchall()
        ]
        release_sources = [
            dict(row)
            for row in conn.execute("SELECT * FROM release_sources").fetchall()
        ]
        decisions = [
            dict(row)
            for row in conn.execute(
                "SELECT source_key, ignored FROM discovery_decisions"
            ).fetchall()
        ]
    return {
        "schema_version": SCHEMA_VERSION,
        "exported_at": _now(),
        "registry_revision": store.registry_revision,
        "services": services,
        "service_components": components,
        "component_overrides": overrides,
        "endpoints": endpoints,
        "port_notes": port_notes,
        "release_sources": release_sources,
        "discovery_decisions": decisions,
    }


def _counts(payload: dict[str, Any]) -> dict[str, int]:
    return {
        "services": len(payload.get("services") or []),
        "service_components": len(payload.get("service_components") or []),
        "endpoints": len(payload.get("endpoints") or []),
        "port_notes": len(payload.get("port_notes") or []),
        "release_sources": len(payload.get("release_sources") or []),
        "discovery_decisions": len(payload.get("discovery_decisions") or []),
    }


def current_counts(store: Store) -> dict[str, int]:
    with store.read() as conn:
        return {
            "services": conn.execute("SELECT COUNT(*) AS c FROM services").fetchone()["c"],
            "service_components": conn.execute(
                "SELECT COUNT(*) AS c FROM service_components"
            ).fetchone()["c"],
            "endpoints": conn.execute("SELECT COUNT(*) AS c FROM endpoints").fetchone()["c"],
            "port_notes": conn.execute("SELECT COUNT(*) AS c FROM port_notes").fetchone()["c"],
            "release_sources": conn.execute(
                "SELECT COUNT(*) AS c FROM release_sources"
            ).fetchone()["c"],
            "discovery_decisions": conn.execute(
                "SELECT COUNT(*) AS c FROM discovery_decisions"
            ).fetchone()["c"],
        }


def parse_and_validate(raw: bytes) -> dict[str, Any]:
    if len(raw) > MAX_BYTES:
        raise BackupError("payload_too_large", f"文件超过 {MAX_BYTES // 1024 // 1024} MiB")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BackupError("invalid_json", f"JSON 解析失败: {exc}") from exc
    if not isinstance(payload, dict):
        raise BackupError("invalid_json", "顶层必须是对象")
    version = payload.get("schema_version")
    if version != SCHEMA_VERSION:
        raise BackupError(
            "unsupported_schema",
            f"不支持的 schema_version={version}（本版本只接受 {SCHEMA_VERSION}）",
        )
    services = payload.get("services")
    if not isinstance(services, list):
        raise BackupError("invalid_shape", "services 必须是数组")
    if len(services) > MAX_SERVICES:
        raise BackupError("payload_too_large", f"服务数超过 {MAX_SERVICES}")
    endpoints = payload.get("endpoints") or []
    if not isinstance(endpoints, list):
        raise BackupError("invalid_shape", "endpoints 必须是数组")
    if len(endpoints) > MAX_ENDPOINTS:
        raise BackupError("payload_too_large", f"入口数超过 {MAX_ENDPOINTS}")
    # 结构完整性（外键 / 唯一）在临时库里验证，不碰生产库
    _validate_relations(payload)
    return payload


def _validate_relations(payload: dict[str, Any]) -> None:
    service_ids: set[str] = set()
    for item in payload.get("services") or []:
        if not isinstance(item, dict):
            raise BackupError("invalid_shape", "services 元素必须是对象")
        service_id = item.get("id")
        if not isinstance(service_id, str) or not service_id:
            raise BackupError("invalid_shape", "服务缺少 id")
        if service_id in service_ids:
            raise BackupError("duplicate_id", f"服务 id 重复: {service_id}")
        service_ids.add(service_id)
        for field_name in ("name", "created_at", "updated_at"):
            if not isinstance(item.get(field_name), str) or not item.get(field_name):
                raise BackupError(
                    "invalid_shape", f"服务 {service_id} 缺少 {field_name}"
                )
    seen_keys: set[str] = set()
    for item in payload.get("service_components") or []:
        if not isinstance(item, dict):
            raise BackupError("invalid_shape", "service_components 元素必须是对象")
        reference = item.get("service_id")
        if reference not in service_ids:
            raise BackupError(
                "missing_foreign_key", f"组件引用了不存在的服务: {reference}"
            )
        source_key = item.get("source_key")
        if not isinstance(source_key, str) or not source_key:
            raise BackupError("invalid_shape", "组件缺少 source_key")
        if source_key in seen_keys:
            raise BackupError("duplicate_binding", f"组件重复绑定: {source_key}")
        seen_keys.add(source_key)
    for table in ("endpoints", "port_notes", "release_sources"):
        seen_source: set[str] = set()
        for item in payload.get(table) or []:
            if not isinstance(item, dict):
                raise BackupError("invalid_shape", f"{table} 元素必须是对象")
            reference = item.get("service_id")
            if reference not in service_ids:
                raise BackupError(
                    "missing_foreign_key", f"{table} 引用了不存在的服务: {reference}"
                )
            if table == "release_sources":
                if reference in seen_source:
                    raise BackupError(
                        "duplicate_binding", f"服务重复关联仓库: {reference}"
                    )
                seen_source.add(reference)
    known_ids = {
        str(item.get("id")) for item in payload.get("endpoints") or [] if item.get("id")
    }
    if len(known_ids) != len(payload.get("endpoints") or []):
        raise BackupError("duplicate_id", "入口 id 重复或缺失")


@dataclass
class Preview:
    digest: str
    registry_revision: int
    counts: dict[str, int]
    current_counts: dict[str, int]
    warnings: list[str]
    payload: dict[str, Any]


def preview(store: Store, raw: bytes) -> Preview:
    payload = parse_and_validate(raw)
    warnings: list[str] = []
    if _counts(payload)["services"] == 0:
        warnings.append("文件不含任何服务，恢复会清空当前人工台账")
    return Preview(
        digest=digest_of(raw),
        registry_revision=store.registry_revision,
        counts=_counts(payload),
        current_counts=current_counts(store),
        warnings=warnings,
        payload=payload,
    )


def legacy_ownership_inputs(
    payload: dict[str, Any], service_id: str
) -> tuple[int, list[str]]:
    """旧备份没有归属字段时，从备份内容还原旧口径需要的输入。

    返回 (组件数, compose 项目列表)：老备份里归属只能按这个推。
    """
    count = 0
    projects: list[str] = []
    for item in payload.get("service_components") or []:
        if item.get("service_id") != service_id:
            continue
        count += 1
        project = project_from_source_key(item.get("source_key") or "")
        if project and project not in projects:
            projects.append(project)
    return count, projects


def restore(
    store: Store,
    *,
    payload: dict[str, Any],
    expected_digest: str,
    expected_revision: int,
    raw: bytes,
    confirm: bool,
    data_dir,
    own_projects: tuple[str, ...] = (),
) -> dict[str, Any]:
    if not confirm:
        raise bad_request("恢复需要 confirm=true")
    if digest_of(raw) != expected_digest:
        raise conflict("文件与预览时不一致，请重新预览", code="digest_mismatch")
    if store.registry_revision != expected_revision:
        raise conflict(
            "预览后台账已变化，请重新预览", code="revision_changed"
        )
    backup_path = data_dir / "backups" / f"pre-restore-{_now().replace(':', '')}.sqlite3"
    store.backup_to(backup_path)
    now = _now()
    with store.transaction() as conn:
        for table in MANUAL_TABLES:
            conn.execute(f"DELETE FROM {table}")
        # 关联缓存与检查结果随人工台账一起作废；发布已读在下次同步重建基线
        conn.execute("DELETE FROM check_results")
        conn.execute("DELETE FROM release_reads")
        conn.execute("UPDATE release_sync SET baseline_done = 0, etag = NULL")
        for item in payload.get("services") or []:
            ownership = item.get("ownership") or ""
            if ownership not in (Ownership.MINE.value, Ownership.OTHER.value):
                # 旧备份没有归属字段：按旧口径兜底，避免恢复后全落一边
                count, projects = legacy_ownership_inputs(payload, item["id"])
                ownership = default_ownership(count, projects, own_projects).value
            conn.execute(
                "INSERT INTO services(id, name, description, category, tags, notes,"
                " ownership, revision, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    item["id"],
                    item["name"],
                    item.get("description", ""),
                    item.get("category", ""),
                    item.get("tags", "[]"),
                    item.get("notes", ""),
                    ownership,
                    int(item.get("revision", 1)),
                    item["created_at"],
                    item["updated_at"],
                ),
            )
        for item in payload.get("service_components") or []:
            conn.execute(
                "INSERT INTO service_components(id, service_id, source_key, required,"
                " label, created_at) VALUES (?,?,?,?,?,?)",
                (
                    item.get("id") or str(uuid.uuid4()),
                    item["service_id"],
                    item["source_key"],
                    int(item.get("required", 1)),
                    item.get("label", ""),
                    item.get("created_at") or now,
                ),
            )
        for item in payload.get("component_overrides") or []:
            conn.execute(
                "INSERT INTO component_overrides(source_key, working_dir,"
                " config_files, data_paths, version_note, updated_at)"
                " VALUES (?,?,?,?,?,?)",
                (
                    item["source_key"],
                    item.get("working_dir"),
                    item.get("config_files"),
                    item.get("data_paths"),
                    item.get("version_note"),
                    item.get("updated_at") or now,
                ),
            )
        for item in payload.get("endpoints") or []:
            conn.execute(
                "INSERT INTO endpoints(id, service_id, label, kind, url, probe_url,"
                " enabled, expected_status_ranges, tls_check, route_target,"
                " renewal_note, revision, created_at, updated_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    item.get("id") or str(uuid.uuid4()),
                    item["service_id"],
                    item.get("label", ""),
                    item.get("kind", "external"),
                    item["url"],
                    item.get("probe_url"),
                    int(item.get("enabled", 1)),
                    item.get("expected_status_ranges", "[]"),
                    int(item.get("tls_check", 1)),
                    item.get("route_target"),
                    item.get("renewal_note", ""),
                    int(item.get("revision", 1)),
                    item.get("created_at") or now,
                    item.get("updated_at") or now,
                ),
            )
        for item in payload.get("port_notes") or []:
            conn.execute(
                "INSERT INTO port_notes(id, service_id, host_ip, host_port,"
                " container_port, protocol, note, revision, created_at, updated_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    item.get("id") or str(uuid.uuid4()),
                    item["service_id"],
                    item.get("host_ip", ""),
                    int(item["host_port"]),
                    item.get("container_port"),
                    item.get("protocol", "tcp"),
                    item.get("note", ""),
                    int(item.get("revision", 1)),
                    item.get("created_at") or now,
                    item.get("updated_at") or now,
                ),
            )
        for item in payload.get("release_sources") or []:
            conn.execute(
                "INSERT INTO release_sources(id, service_id, owner, repo,"
                " installed_tag_note, revision, created_at, updated_at)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (
                    item.get("id") or str(uuid.uuid4()),
                    item["service_id"],
                    item["owner"],
                    item["repo"],
                    item.get("installed_tag_note", ""),
                    int(item.get("revision", 1)),
                    item.get("created_at") or now,
                    item.get("updated_at") or now,
                ),
            )
        for item in payload.get("discovery_decisions") or []:
            conn.execute(
                "INSERT INTO discovery_decisions(source_key, ignored, updated_at)"
                " VALUES (?,?,?)",
                (
                    item["source_key"],
                    int(item.get("ignored", 0)),
                    item.get("updated_at") or now,
                ),
            )
        Store.bump_registry_revision(conn)
    return {
        "restored": current_counts(store),
        "backup_path": str(backup_path),
        "registry_revision": store.registry_revision,
    }
