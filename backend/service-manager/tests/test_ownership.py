"""归属（ownership）：逐条可设的「我维护的 / 别人的」。

旧口径是按 compose 项目名单全局推导分 tab；现在归属落在 services.ownership 上，
页面可逐条改。默认口径沿用旧规则，保证新建/回填时分组不变。
"""

from __future__ import annotations

import json
import sqlite3

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from src.backup import export_payload, preview, restore
from src.db import Store
from src.discovery import DiscoveryService
from src.models import (
    DiscoveryImportItem,
    DiscoveryImportRequest,
    ServiceCreate,
    ServicePatch,
)
from src.registry import Registry, default_ownership
from src.main import build_app
from tests.conftest import FakeReader, container_payload

OWN = ("personal-web",)


@pytest.fixture()
def client(settings):
    app = build_app(settings)
    with TestClient(app) as test_client:
        yield test_client


def make_discovery(store, registry, payloads) -> DiscoveryService:
    reader = FakeReader(payloads)
    service = DiscoveryService(store, registry, reader)
    service.run_scan()
    return service


# ---------------------------------------------------------------------------
# 默认口径
# ---------------------------------------------------------------------------


def test_default_ownership_follows_legacy_rule() -> None:
    # 没关联容器（人工登记）→ 我维护的
    assert default_ownership(0, [], OWN) == "mine"
    # 项目命中 own 名单 → 我维护的
    assert default_ownership(1, ["personal-web"], OWN) == "mine"
    # 项目不在名单 → 别人的
    assert default_ownership(1, ["immich"], OWN) == "other"
    # 有容器但没有 compose 标签 → 别人的
    assert default_ownership(1, [], OWN) == "other"


def test_manual_service_defaults_to_mine(registry: Registry) -> None:
    detail = registry.create_service(ServiceCreate(name="手工登记"))
    assert detail.ownership == "mine"


def test_import_new_service_ownership_follows_project(registry: Registry, store) -> None:
    service = make_discovery(
        store,
        registry,
        [
            container_payload(project="personal-web", service="front"),
            container_payload(
                project="immich", service="server", container_id="b" * 64
            ),
        ],
    )
    mine = service.import_components(
        DiscoveryImportRequest(
            components=[
                DiscoveryImportItem(source_key="nas:compose:personal-web:front:1")
            ],
            name="我的服务",
        ),
        OWN,
    )
    other = service.import_components(
        DiscoveryImportRequest(
            components=[
                DiscoveryImportItem(source_key="nas:compose:immich:server:1")
            ],
            name="别人的服务",
        ),
        OWN,
    )
    assert registry.get_service(mine["service_id"]).ownership == "mine"
    assert registry.get_service(other["service_id"]).ownership == "other"


def test_import_appending_keeps_existing_ownership(registry: Registry, store) -> None:
    service = make_discovery(
        store,
        registry,
        [container_payload(project="immich", service="server")],
    )
    created = service.import_components(
        DiscoveryImportRequest(
            components=[
                DiscoveryImportItem(source_key="nas:compose:immich:server:1")
            ],
            name="别人的服务",
        ),
        OWN,
    )
    assert registry.get_service(created["service_id"]).ownership == "other"


# ---------------------------------------------------------------------------
# 逐条改
# ---------------------------------------------------------------------------


def test_patch_ownership_changes_grouping(registry: Registry) -> None:
    detail = registry.create_service(ServiceCreate(name="相册"))
    updated = registry.update_service(
        detail.id,
        ServicePatch(revision=detail.revision, ownership="other"),
    )
    assert updated.ownership == "other"
    items, _ = registry.list_services()
    assert items[0].ownership == "other"


def test_patch_rejects_unknown_ownership(registry: Registry) -> None:
    detail = registry.create_service(ServiceCreate(name="相册"))
    with pytest.raises(ValidationError):
        ServicePatch(revision=detail.revision, ownership="everyone")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 旧库回填
# ---------------------------------------------------------------------------


def test_backfill_ownership_only_touches_unset_rows(registry: Registry, store) -> None:
    mine = registry.create_service(ServiceCreate(name="我的"))
    other = registry.create_service(ServiceCreate(name="别人的"))
    # 模拟旧库：归属列空
    with store.transaction() as conn:
        conn.execute("UPDATE services SET ownership = '' WHERE id = ?", (other.id,))
        conn.execute(
            "INSERT INTO service_components(id, service_id, source_key, required,"
            " label, created_at) VALUES ('c1', ?, 'nas:compose:immich:server:1', 1,"
            " '', '2026-01-01T00:00:00+00:00')",
            (other.id,),
        )
    changed = registry.backfill_ownership(OWN)
    assert changed == 1
    assert registry.get_service(other.id).ownership == "other"
    assert registry.get_service(mine.id).ownership == "mine"
    # 再跑一次没有可回填的行
    assert registry.backfill_ownership(OWN) == 0


def test_backfill_does_not_override_user_choice(registry: Registry, store) -> None:
    detail = registry.create_service(ServiceCreate(name="我改过的"))
    registry.update_service(detail.id, ServicePatch(revision=1, ownership="other"))
    with store.transaction() as conn:
        conn.execute("UPDATE services SET ownership = '' WHERE id = ?", (detail.id,))
    registry.backfill_ownership(OWN)
    assert registry.get_service(detail.id).ownership == "mine"


def test_add_column_migration_for_existing_database(settings, tmp_path) -> None:
    """旧库里没有 ownership 列时，启动要能补列而不是崩。"""
    path = settings.data_dir / "service-manager.sqlite3"
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE services (id TEXT PRIMARY KEY, name TEXT NOT NULL,"
        " description TEXT NOT NULL DEFAULT '', category TEXT NOT NULL DEFAULT '',"
        " tags TEXT NOT NULL DEFAULT '[]', notes TEXT NOT NULL DEFAULT '',"
        " revision INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL,"
        " updated_at TEXT NOT NULL)"
    )
    conn.execute(
        "INSERT INTO services(id, name, created_at, updated_at)"
        " VALUES ('old', '旧服务', '2026-01-01T00:00:00+00:00',"
        " '2026-01-01T00:00:00+00:00')"
    )
    conn.commit()
    conn.close()

    store = Store.from_settings(settings)
    with store.read() as conn:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(services)")}
        row = conn.execute("SELECT ownership FROM services WHERE id = 'old'").fetchone()
    assert "ownership" in columns
    assert row["ownership"] == ""


# ---------------------------------------------------------------------------
# 备份恢复
# ---------------------------------------------------------------------------


def test_backup_roundtrip_keeps_ownership(registry: Registry, store, settings) -> None:
    detail = registry.create_service(ServiceCreate(name="相册"))
    registry.update_service(detail.id, ServicePatch(revision=1, ownership="other"))
    payload = export_payload(store)
    assert payload["services"][0]["ownership"] == "other"

    registry.delete_service(detail.id)
    raw = json.dumps(payload).encode()
    meta = preview(store, raw)
    restore(
        store,
        payload=meta.payload,
        expected_digest=meta.digest,
        expected_revision=meta.registry_revision,
        raw=raw,
        confirm=True,
        data_dir=settings.data_dir,
        own_projects=OWN,
    )
    assert registry.get_service(detail.id).ownership == "other"


def test_restore_old_backup_falls_back_to_legacy_rule(
    registry: Registry, store, settings
) -> None:
    """老备份没有归属字段：按旧口径兜底，不要全落一边。"""
    detail = registry.create_service(ServiceCreate(name="别人的"))
    with store.transaction() as conn:
        conn.execute(
            "INSERT INTO service_components(id, service_id, source_key, required,"
            " label, created_at) VALUES ('c1', ?, 'nas:compose:immich:server:1', 1,"
            " '', '2026-01-01T00:00:00+00:00')",
            (detail.id,),
        )
    payload = export_payload(store)
    for item in payload["services"]:
        item.pop("ownership", None)

    registry.delete_service(detail.id)
    raw = json.dumps(payload).encode()
    meta = preview(store, raw)
    restore(
        store,
        payload=meta.payload,
        expected_digest=meta.digest,
        expected_revision=meta.registry_revision,
        raw=raw,
        confirm=True,
        data_dir=settings.data_dir,
        own_projects=OWN,
    )
    assert registry.get_service(detail.id).ownership == "other"


def test_api_patch_ownership(client) -> None:
    client.post("/api/auth/login", json={"password": "test-password"})
    created = client.post(
        "/api/services", json={"name": "相册"}, headers={"Origin": "http://localhost:3012"}
    )
    assert created.status_code == 201
    service_id = created.json()["id"]
    assert created.json()["ownership"] == "mine"

    patched = client.patch(
        f"/api/services/{service_id}",
        json={"revision": created.json()["revision"], "ownership": "other"},
        headers={"Origin": "http://localhost:3012"},
    )
    assert patched.status_code == 200
    assert patched.json()["ownership"] == "other"

    listed = client.get("/api/services")
    assert listed.json()["items"][0]["ownership"] == "other"


def test_api_rejects_invalid_ownership(client) -> None:
    client.post("/api/auth/login", json={"password": "test-password"})
    created = client.post(
        "/api/services", json={"name": "相册"}, headers={"Origin": "http://localhost:3012"}
    )
    service_id = created.json()["id"]
    patched = client.patch(
        f"/api/services/{service_id}",
        json={"revision": created.json()["revision"], "ownership": "everyone"},
        headers={"Origin": "http://localhost:3012"},
    )
    # 校验失败统一 400（错误契约：code/message/field_errors）
    assert patched.status_code == 400
