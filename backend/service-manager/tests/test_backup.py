"""导出 / 恢复（A12）。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src import errors
from src.backup import BackupError, digest_of, export_payload, preview, restore
from src.models import EndpointInput, PortNoteInput, ReleaseSourceInput, ServiceCreate
from src.registry import Registry


def seed(registry: Registry, store) -> None:
    service = registry.create_service(
        ServiceCreate(name="股息率", description="d", category="金融", tags=["public"])
    )
    registry.add_endpoint(
        service.id, EndpointInput(url="https://web.duomi77.cn:9443/dividend", label="web")
    )
    registry.add_port_note(service.id, PortNoteInput(host_ip="0.0.0.0", host_port=3011))
    registry.set_release_source(service.id, ReleaseSourceInput(owner="o", repo="r"))
    registry.set_ignored(["nas:container:abc"], True)
    with store.transaction() as conn:
        registry.bind_component(conn, service.id, "nas:compose:p:s:1")


def test_export_shape_and_exclusions(registry: Registry, store) -> None:
    seed(registry, store)
    payload = export_payload(store)
    assert payload["schema_version"] == 1
    assert len(payload["services"]) == 1
    assert len(payload["endpoints"]) == 1
    assert len(payload["port_notes"]) == 1
    assert len(payload["release_sources"]) == 1
    assert len(payload["discovery_decisions"]) == 1
    blob = json.dumps(payload)
    for forbidden in (
        "check_results",
        "refresh_jobs",
        "release_reads",
        "docker_components",
        "password",
        "session",
        "token",
    ):
        assert forbidden not in blob


def test_roundtrip_restores_manual_ledger(registry: Registry, store, settings) -> None:
    seed(registry, store)
    payload = export_payload(store)
    raw = json.dumps(payload).encode()
    # 清空台账（这会推进 registry_revision，所以恢复前必须重新预览）
    registry.delete_service(payload["services"][0]["id"])
    assert registry.list_services()[1] == 0
    meta = preview(store, raw)
    result = restore(
        store,
        payload=meta.payload,
        expected_digest=meta.digest,
        expected_revision=meta.registry_revision,
        raw=raw,
        confirm=True,
        data_dir=settings.data_dir,
    )
    assert result["restored"]["services"] == 1
    assert result["restored"]["endpoints"] == 1
    assert Path(result["backup_path"]).exists()


def test_restore_requires_confirm(registry: Registry, store, settings) -> None:
    seed(registry, store)
    raw = json.dumps(export_payload(store)).encode()
    meta = preview(store, raw)
    with pytest.raises(errors.ApiError):
        restore(
            store,
            payload=meta.payload,
            expected_digest=meta.digest,
            expected_revision=meta.registry_revision,
            raw=raw,
            confirm=False,
            data_dir=settings.data_dir,
        )


def test_restore_rejects_stale_revision(registry: Registry, store, settings) -> None:
    seed(registry, store)
    raw = json.dumps(export_payload(store)).encode()
    meta = preview(store, raw)
    registry.create_service(ServiceCreate(name="new one"))
    with pytest.raises(errors.ApiError) as exc:
        restore(
            store,
            payload=meta.payload,
            expected_digest=meta.digest,
            expected_revision=meta.registry_revision,
            raw=raw,
            confirm=True,
            data_dir=settings.data_dir,
        )
    assert exc.value.code == "revision_changed"


def test_preview_rejects_duplicate_binding(registry: Registry, store) -> None:
    payload = {
        "schema_version": 1,
        "services": [
            {"id": "s1", "name": "a", "created_at": "x", "updated_at": "x"},
            {"id": "s2", "name": "b", "created_at": "x", "updated_at": "x"},
        ],
        "service_components": [
            {"id": "c1", "service_id": "s1", "source_key": "k"},
            {"id": "c2", "service_id": "s2", "source_key": "k"},
        ],
    }
    with pytest.raises(BackupError) as exc:
        preview(store, json.dumps(payload).encode())
    assert exc.value.code == "duplicate_binding"


def test_preview_rejects_missing_foreign_key(registry: Registry, store) -> None:
    payload = {
        "schema_version": 1,
        "services": [],
        "endpoints": [{"id": "e", "service_id": "nope", "url": "https://x/"}],
    }
    with pytest.raises(BackupError) as exc:
        preview(store, json.dumps(payload).encode())
    assert exc.value.code == "missing_foreign_key"


def test_preview_rejects_broken_json(registry: Registry, store) -> None:
    with pytest.raises(BackupError) as exc:
        preview(store, b"{not json")
    assert exc.value.code == "invalid_json"


def test_preview_rejects_oversized(registry: Registry, store) -> None:
    raw = b'{"schema_version":1,"services":[]}' + b" " * (5 * 1024 * 1024 + 1)
    with pytest.raises(BackupError) as exc:
        preview(store, raw)
    assert exc.value.code == "payload_too_large"


def test_preview_rejects_unsupported_schema(registry: Registry, store) -> None:
    with pytest.raises(BackupError) as exc:
        preview(store, json.dumps({"schema_version": 2, "services": []}).encode())
    assert exc.value.code == "unsupported_schema"


def test_restore_clears_checks_and_release_reads(registry: Registry, store, settings) -> None:
    seed(registry, store)
    service_id = export_payload(store)["services"][0]["id"]
    with store.transaction() as conn:
        conn.execute(
            "INSERT INTO check_results(target_type, target_id, check_kind,"
            " check_status) VALUES ('service', ?, 'releases', 'success')",
            (service_id,),
        )
        conn.execute(
            "INSERT INTO release_reads(release_source_id, release_id, read_at)"
            " VALUES ('src', 1, 'x')"
        )
    raw = json.dumps(export_payload(store)).encode()
    meta = preview(store, raw)
    restore(
        store,
        payload=meta.payload,
        expected_digest=meta.digest,
        expected_revision=meta.registry_revision,
        raw=raw,
        confirm=True,
        data_dir=settings.data_dir,
    )
    with store.read() as conn:
        checks = conn.execute("SELECT COUNT(*) AS c FROM check_results").fetchone()["c"]
        reads = conn.execute("SELECT COUNT(*) AS c FROM release_reads").fetchone()["c"]
        sync = conn.execute(
            "SELECT baseline_done FROM release_sync"
        ).fetchall()
    assert checks == 0
    assert reads == 0


def test_restore_is_atomic_on_failure(registry: Registry, store, settings) -> None:
    """恢复中途失败 → 整笔回滚，原台账不丢。"""
    seed(registry, store)
    before = export_payload(store)["services"]
    raw = json.dumps(export_payload(store)).encode()
    meta = preview(store, raw)
    bad_payload = json.loads(raw)
    # 造一个能过 preview 但插入期违反唯一约束的数据（重复 endpoint id）
    bad_payload["endpoints"] = [
        bad_payload["endpoints"][0],
        {**bad_payload["endpoints"][0], "url": "https://other/"},
    ]
    with pytest.raises(Exception):
        restore(
            store,
            payload=bad_payload,
            expected_digest=meta.digest,
            expected_revision=meta.registry_revision,
            raw=raw,
            confirm=True,
            data_dir=settings.data_dir,
        )
    after = export_payload(store)["services"]
    assert [item["id"] for item in after] == [item["id"] for item in before]


def test_backup_files_are_written(registry: Registry, store, settings) -> None:
    seed(registry, store)
    raw = json.dumps(export_payload(store)).encode()
    meta = preview(store, raw)
    result = restore(
        store,
        payload=meta.payload,
        expected_digest=meta.digest,
        expected_revision=meta.registry_revision,
        raw=raw,
        confirm=True,
        data_dir=settings.data_dir,
    )
    assert (settings.data_dir / "backups").is_dir()
    assert Path(result["backup_path"]).stat().st_size > 0
