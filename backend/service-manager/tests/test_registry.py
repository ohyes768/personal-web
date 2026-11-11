"""台账 CRUD 与 revision 契约（A1 / A2）。"""

from __future__ import annotations

import pytest

from src import errors
from src.models import (
    EndpointInput,
    PortNoteInput,
    ReleaseSourceInput,
    RouteTarget,
    ServiceCreate,
    ServicePatch,
)
from src.registry import Registry


def test_create_and_get_service(registry: Registry) -> None:
    detail = registry.create_service(
        ServiceCreate(name="股息率", category="金融", tags=["public", "public", "stock"])
    )
    assert detail.id
    assert detail.name == "股息率"
    assert detail.tags == ["public", "stock"]
    assert detail.revision == 1
    assert detail.created_at.endswith("+00:00")


def test_list_services_paginates(registry: Registry) -> None:
    for index in range(3):
        registry.create_service(ServiceCreate(name=f"svc-{index}"))
    items, total = registry.list_services(page=1, page_size=2)
    assert total == 3
    assert len(items) == 2
    items2, _ = registry.list_services(page=2, page_size=2)
    assert len(items2) == 1


def test_list_services_search_matches_name_and_url(registry: Registry) -> None:
    target = registry.create_service(ServiceCreate(name="股票行情"))
    registry.create_service(ServiceCreate(name="其他"))
    registry.add_endpoint(
        target.id,
        EndpointInput(url="https://web.duomi77.cn:9443/dividend", label="dividend"),
    )
    items, total = registry.list_services(query="duomi77")
    assert total == 1
    assert items[0].id == target.id
    assert items[0].primary_url == "https://web.duomi77.cn:9443/dividend"


def test_blank_name_rejected() -> None:
    with pytest.raises(ValueError):
        ServiceCreate(name="   ")


def test_patch_requires_matching_revision(registry: Registry) -> None:
    detail = registry.create_service(ServiceCreate(name="a"))
    updated = registry.update_service(detail.id, ServicePatch(name="b", revision=1))
    assert updated.name == "b"
    assert updated.revision == 2
    with pytest.raises(errors.ApiError) as exc:
        registry.update_service(detail.id, ServicePatch(name="c", revision=1))
    assert exc.value.status_code == 409
    assert exc.value.code == "revision_conflict"


def test_patch_partial_leaves_other_fields(registry: Registry) -> None:
    detail = registry.create_service(
        ServiceCreate(name="a", description="d", category="c", tags=["t"])
    )
    updated = registry.update_service(detail.id, ServicePatch(notes="n", revision=1))
    assert updated.description == "d"
    assert updated.category == "c"
    assert updated.tags == ["t"]
    assert updated.notes == "n"


def test_delete_removes_ledger_only(registry: Registry, store) -> None:
    detail = registry.create_service(ServiceCreate(name="a"))
    registry.delete_service(detail.id)
    with pytest.raises(errors.ApiError) as exc:
        registry.get_service(detail.id)
    assert exc.value.status_code == 404
    # 只删台账：不产生任何 Docker 写操作（本模块根本没有这类调用）
    assert store.get_state("docker_last_error") is None


def test_registry_revision_bumps_on_mutation(registry: Registry, store) -> None:
    before = store.registry_revision
    registry.create_service(ServiceCreate(name="a"))
    assert store.registry_revision == before + 1


def test_duplicate_component_binding_conflicts(registry: Registry, store) -> None:
    first = registry.create_service(ServiceCreate(name="a"))
    second = registry.create_service(ServiceCreate(name="b"))
    with store.transaction() as conn:
        registry.bind_component(conn, first.id, "nas:compose:p:s:1")
    with pytest.raises(errors.ApiError) as exc:
        with store.transaction() as conn:
            registry.bind_component(conn, second.id, "nas:compose:p:s:1")
    assert exc.value.code == "duplicate_binding"


def test_endpoint_rejects_userinfo_and_metadata(registry: Registry) -> None:
    detail = registry.create_service(ServiceCreate(name="a"))
    with pytest.raises(errors.ApiError):
        registry.add_endpoint(detail.id, EndpointInput(url="https://u:p@host/x"))
    with pytest.raises(errors.ApiError):
        registry.add_endpoint(detail.id, EndpointInput(url="http://169.254.169.254/"))
    with pytest.raises(errors.ApiError):
        registry.add_endpoint(detail.id, EndpointInput(url="ftp://host/x"))


def test_endpoint_rejects_credential_query(registry: Registry) -> None:
    detail = registry.create_service(ServiceCreate(name="a"))
    with pytest.raises(errors.ApiError):
        registry.add_endpoint(
            detail.id, EndpointInput(url="https://host/x?access_token=abc")
        )


def test_endpoint_allows_lan_and_domain_paths(registry: Registry) -> None:
    detail = registry.create_service(ServiceCreate(name="a"))
    lan = registry.add_endpoint(
        detail.id, EndpointInput(url="http://192.168.31.73:8097/api/health")
    )
    assert lan.url.startswith("http://192.168.31.73")
    path_a = registry.add_endpoint(
        detail.id,
        EndpointInput(
            url="https://web.duomi77.cn:9443/a",
            kind="external",
        ),
    )
    path_b = registry.add_endpoint(
        detail.id,
        EndpointInput(
            url="https://web.duomi77.cn:9443/b",
            route_target=RouteTarget(host="dividend-frontend", port=3003, path_prefix="/"),
        ),
    )
    assert path_a.id != path_b.id
    assert path_b.route_target is not None
    assert path_b.route_target.port == 3003


def test_endpoint_probe_url_rejects_localhost(registry: Registry) -> None:
    detail = registry.create_service(ServiceCreate(name="a"))
    with pytest.raises(errors.ApiError) as exc:
        registry.add_endpoint(
            detail.id,
            EndpointInput(
                url="https://web.duomi77.cn:9443/a",
                probe_url="http://localhost:3003/",
            ),
        )
    assert "localhost" in exc.value.message


def test_endpoint_expected_status_range_validated(registry: Registry) -> None:
    detail = registry.create_service(ServiceCreate(name="a"))
    with pytest.raises(errors.ApiError):
        registry.add_endpoint(
            detail.id,
            EndpointInput(url="https://h/x", expected_status_ranges=["999"]),
        )
    ok = registry.add_endpoint(
        detail.id, EndpointInput(url="https://h/x", expected_status_ranges=["200-399"])
    )
    assert ok.expected_status_ranges == ["200-399"]


def test_port_note_and_release_source(registry: Registry) -> None:
    detail = registry.create_service(ServiceCreate(name="a"))
    note = registry.add_port_note(
        detail.id, PortNoteInput(host_ip="0.0.0.0", host_port=3011, note="残留")
    )
    assert note.host_port == 3011
    source = registry.set_release_source(
        detail.id, ReleaseSourceInput(owner="zzet", repo="immich")
    )
    assert source.owner == "zzet"
    again = registry.set_release_source(
        detail.id, ReleaseSourceInput(owner="zzet", repo="immich", installed_tag_note="v1.0")
    )
    assert again.revision == 2
    assert again.installed_tag_note == "v1.0"


def test_ignored_decisions_persist(registry: Registry) -> None:
    registry.set_ignored(["nas:container:abc"], True)
    assert "nas:container:abc" in registry.ignored_keys()
    registry.set_ignored(["nas:container:abc"], False)
    assert "nas:container:abc" not in registry.ignored_keys()
