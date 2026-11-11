"""发现、导入与关联稳定性（A2 / A3 / A4）。"""

from __future__ import annotations

import pytest

from src import errors
from src.discovery import DiscoveryService
from src.docker_reader import DockerUnavailable
from src.models import DiscoveryImportItem, DiscoveryImportRequest, ServiceCreate
from src.registry import Registry
from tests.conftest import FakeReader, container_payload


def make(store, registry, payloads):
    return DiscoveryService(store, registry, FakeReader(payloads))


def test_scan_publishes_all_components(store, registry) -> None:
    service = make(
        store,
        registry,
        [
            container_payload(service="dividend-frontend", container_id="a" * 64),
            container_payload(service="dividend-backend", container_id="b" * 64),
        ],
    )
    snapshot = service.run_scan()
    assert snapshot.ok is True
    components = service.components()
    assert len(components) == 2
    assert service.last_success_at() is not None


def test_scan_failure_keeps_previous_observation(store, registry) -> None:
    reader = FakeReader([container_payload()])
    service = DiscoveryService(store, registry, reader)
    service.run_scan()
    assert len(service.components()) == 1
    reader.fail_with = DockerUnavailable("connection refused")
    snapshot = service.run_scan()
    assert snapshot.ok is False
    # 旧观测保留；不把采集失败当成 missing
    components = service.components()
    assert len(components) == 1
    assert list(components.values())[0]["state"] == "running"
    available, error = service.scan_available()
    assert error == "connection refused"


def test_scan_without_reader_reports_unavailable(store, registry) -> None:
    service = DiscoveryService(store, registry, None)
    snapshot = service.run_scan()
    assert snapshot.ok is False
    available, error = service.scan_available()
    assert available is False
    assert "未配置" in (error or "")


def test_missing_marked_only_after_successful_rescan(store, registry) -> None:
    reader = FakeReader(
        [
            container_payload(service="a", container_id="a" * 64),
            container_payload(service="b", container_id="b" * 64),
        ]
    )
    service = DiscoveryService(store, registry, reader)
    service.run_scan()
    reader.payloads = [container_payload(service="a", container_id="a" * 64)]
    service.run_scan()
    components = service.components()
    states = {key: item["state"] for key, item in components.items()}
    assert states["nas:compose:personal-web:a:1"] == "running"
    assert states["nas:compose:personal-web:b:1"] == "missing"


def test_rebuild_keeps_binding(store, registry) -> None:
    reader = FakeReader([container_payload(service="a", container_id="a" * 64)])
    service = DiscoveryService(store, registry, reader)
    service.run_scan()
    created = service.import_components(
        DiscoveryImportRequest(
            components=[DiscoveryImportItem(source_key="nas:compose:personal-web:a:1")],
            name="A 服务",
        )
    )
    service_id = created["service_id"]
    # 容器重建：ID 变化，source_key 不变
    reader.payloads = [container_payload(service="a", container_id="c" * 64)]
    service.run_scan()
    detail = registry.get_service(service_id)
    assert len(detail.components) == 0  # 详情由 projector 组装，这里只看绑定
    bindings = registry.list_bindings(service_id)
    assert bindings[0]["source_key"] == "nas:compose:personal-web:a:1"


def test_duplicate_import_conflicts(store, registry) -> None:
    service = make(store, registry, [container_payload()])
    service.run_scan()
    payload = DiscoveryImportRequest(
        components=[DiscoveryImportItem(source_key="nas:compose:personal-web:dividend:1")],
        name="A",
    )
    service.import_components(payload)
    with pytest.raises(errors.ApiError) as exc:
        service.import_components(
            DiscoveryImportRequest(
                components=[
                    DiscoveryImportItem(source_key="nas:compose:personal-web:dividend:1")
                ],
                name="B",
            )
        )
    assert exc.value.code == "duplicate_binding"


def test_import_appends_to_existing_service(store, registry) -> None:
    service = make(
        store,
        registry,
        [
            container_payload(service="front", container_id="a" * 64),
            container_payload(service="back", container_id="b" * 64),
        ],
    )
    service.run_scan()
    first = service.import_components(
        DiscoveryImportRequest(
            components=[DiscoveryImportItem(source_key="nas:compose:personal-web:front:1")],
            name="合并服务",
        )
    )
    second = service.import_components(
        DiscoveryImportRequest(
            components=[DiscoveryImportItem(source_key="nas:compose:personal-web:back:1")],
            service_id=first["service_id"],
        )
    )
    assert second["created"] is False
    bindings = registry.list_bindings(first["service_id"])
    assert len(bindings) == 2


def test_import_requires_name_for_new_service(store, registry) -> None:
    service = make(store, registry, [container_payload()])
    service.run_scan()
    with pytest.raises(errors.ApiError):
        service.import_components(
            DiscoveryImportRequest(
                components=[
                    DiscoveryImportItem(source_key="nas:compose:personal-web:dividend:1")
                ]
            )
        )


def test_import_unknown_candidate_conflicts(store, registry) -> None:
    service = make(store, registry, [container_payload()])
    service.run_scan()
    with pytest.raises(errors.ApiError) as exc:
        service.import_components(
            DiscoveryImportRequest(
                components=[DiscoveryImportItem(source_key="nas:compose:x:y:1")],
                name="A",
            )
        )
    assert exc.value.code == "candidate_missing"


def test_oneoff_not_importable(store, registry) -> None:
    service = make(
        store, registry, [container_payload(service="task", oneoff=True)]
    )
    service.run_scan()
    with pytest.raises(errors.ApiError) as exc:
        service.import_components(
            DiscoveryImportRequest(
                components=[
                    DiscoveryImportItem(source_key="nas:compose:personal-web:task:1")
                ],
                name="A",
            )
        )
    assert exc.value.code == "candidate_ephemeral"


def test_ignored_decisions_survive_rescan(store, registry) -> None:
    service = make(store, registry, [container_payload(service="tmp", container_id="a" * 64)])
    service.run_scan()
    registry.set_ignored(["nas:compose:personal-web:tmp:1"], True)
    service.run_scan()
    candidates = service.candidates()
    assert candidates[0].ignored is True


def test_oneoff_hidden_from_default_candidates(store, registry) -> None:
    service = make(
        store,
        registry,
        [
            container_payload(service="a", container_id="a" * 64),
            container_payload(service="t", oneoff=True, container_id="t" * 64),
        ],
    )
    service.run_scan()
    default = service.candidates()
    assert len(default) == 1
    with_ephemeral = service.candidates(include_ephemeral=True)
    assert len(with_ephemeral) == 2


def test_scan_does_not_overwrite_manual_fields(store, registry) -> None:
    service = make(store, registry, [container_payload()])
    service.run_scan()
    created = service.import_components(
        DiscoveryImportRequest(
            components=[
                DiscoveryImportItem(source_key="nas:compose:personal-web:dividend:1")
            ],
            name="A",
            description="人工写的用途",
        )
    )
    service.run_scan()
    detail = registry.get_service(created["service_id"])
    assert detail.description == "人工写的用途"


def test_scan_does_not_record_raw_inspect(store, registry) -> None:
    payload = container_payload()
    payload["Config"]["Env"] = ["TOP_SECRET=1"]
    service = make(store, registry, [payload])
    service.run_scan()
    with store.read() as conn:
        rows = conn.execute("SELECT * FROM docker_components").fetchall()
    serialized = repr([dict(row) for row in rows])
    assert "TOP_SECRET" not in serialized
