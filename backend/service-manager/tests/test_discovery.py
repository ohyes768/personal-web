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


def test_candidates_bound_filter(store, registry) -> None:
    service = make(
        store,
        registry,
        [
            container_payload(service="a", container_id="a" * 64),
            container_payload(service="b", container_id="b" * 64),
        ],
    )
    service.run_scan()
    created = service.import_components(
        DiscoveryImportRequest(
            components=[DiscoveryImportItem(source_key="nas:compose:personal-web:a:1")],
            name="A 服务",
        )
    )
    service_id = created["service_id"]

    unbound = service.candidates(bound=False)
    assert [row.service_name for row in unbound] == ["b"]
    assert all(row.bound_service_id is None for row in unbound)

    bound_rows = service.candidates(bound=True)
    assert [row.service_name for row in bound_rows] == ["a"]
    assert all(row.bound_service_id == service_id for row in bound_rows)

    assert {row.service_name for row in service.candidates(bound=None)} == {"a", "b"}


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


def _loose_payload(container_id: str, name: str, image: str, state: str = "running"):
    """游离容器（无任何 compose 标签），模拟 docker run --rm 一次性容器。"""
    return container_payload(
        project=None,
        service=None,
        container_id=container_id,
        name=name,
        image=image,
        state=state,
        working_dir=None,
        config_files=None,
    )


def test_loose_missing_rows_are_deleted(store, registry) -> None:
    """游离容器消失后必须删台账，而不是留下永久 missing 候选。"""
    reader = FakeReader(
        [
            container_payload(service="a", container_id="a" * 64),
            _loose_payload("c" * 64, "brave_yalow", "debian:stable-slim"),
        ]
    )
    service = DiscoveryService(store, registry, reader)
    service.run_scan()
    assert "nas:container:" + "c" * 12 in service.components()
    # 容器消失（docker run --rm 退出即删）：compose 容器标 missing，游离容器删除
    reader.payloads = [container_payload(service="a", container_id="a" * 64)]
    service.run_scan()
    components = service.components()
    assert components["nas:compose:personal-web:a:1"]["state"] == "running"
    assert "nas:container:" + "c" * 12 not in components


def test_loose_running_container_hidden_within_grace(store, registry) -> None:
    """游离运行容器在首见宽限期内不作为候选展示，宽限期过后出现。"""
    from datetime import datetime, timedelta, timezone

    reader = FakeReader([_loose_payload("d" * 64, "jolly_einstein", "alpine")])
    service = DiscoveryService(store, registry, reader, ephemeral_grace_seconds=7200)
    seen_at = datetime(2026, 11, 24, 10, 0, 0, tzinfo=timezone.utc)
    service.run_scan(now=seen_at)

    key = "nas:container:" + "d" * 12
    assert service.components()[key]["first_seen_at"] == seen_at.isoformat(timespec="seconds")

    def names(at):
        return {
            row.container_name
            for row in service.candidates(now=at)
        }

    # 首见后 1 小时：仍在宽限期内，不出现
    assert names(seen_at + timedelta(minutes=60)) == set()
    # include_ephemeral=True 仍然可见（保留排查通道）
    assert {
        row.container_name
        for row in service.candidates(include_ephemeral=True, now=seen_at + timedelta(minutes=60))
    } == {"jolly_einstein"}
    # 首见 2 小时后：宽限期已过，作为候选出现
    assert names(seen_at + timedelta(hours=2)) == {"jolly_einstein"}


def test_loose_container_grace_survives_restart(store, registry) -> None:
    """游离容器重启（同 id）不重置首见时间：宽限期从第一次发现起算。"""
    from datetime import datetime, timedelta, timezone

    reader = FakeReader([_loose_payload("e" * 64, "relaxed_elion", "debian:stable-slim")])
    service = DiscoveryService(store, registry, reader, ephemeral_grace_seconds=7200)
    seen_at = datetime(2026, 11, 24, 10, 0, 0, tzinfo=timezone.utc)
    service.run_scan(now=seen_at)
    restarted_at = seen_at + timedelta(minutes=90)
    service.run_scan(now=restarted_at)

    key = "nas:container:" + "e" * 12
    row = service.components()[key]
    assert row["first_seen_at"] == seen_at.isoformat(timespec="seconds")
    assert row["last_seen_at"] == restarted_at.isoformat(timespec="seconds")
    # 重启后离首见 90 分钟，仍在 2h 宽限期内 → 不出现
    assert service.candidates(now=restarted_at) == []


def test_bound_loose_container_not_hidden_by_grace(store, registry) -> None:
    """已绑定/已忽略的游离容器不受宽限期影响。"""
    reader = FakeReader([_loose_payload("f" * 64, "file-system-go", "alpine")])
    service = DiscoveryService(store, registry, reader, ephemeral_grace_seconds=7200)
    from datetime import datetime, timezone

    now = datetime(2026, 11, 24, 10, 0, 0, tzinfo=timezone.utc)
    service.run_scan(now=now)
    key = "nas:container:" + "f" * 12
    service.import_components(
        DiscoveryImportRequest(
            components=[DiscoveryImportItem(source_key=key)],
            name="audio-server",
        )
    )
    assert [
        row.container_name
        for row in service.candidates(bound=True, now=now)
    ] == ["file-system-go"]
