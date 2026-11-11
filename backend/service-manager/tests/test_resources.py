"""端口 / 域名 / 证书投影（A5 / A6）。"""

from __future__ import annotations

from src.discovery import DiscoveryService
from src.models import EndpointInput, PortNoteInput, RouteTarget, ServiceCreate
from src.resources import ResourceProjector, binding_covers, ports_overlap
from src.models import PortView
from tests.conftest import FakeReader, container_payload


def projector(store, registry, payloads) -> ResourceProjector:
    discovery = DiscoveryService(store, registry, FakeReader(payloads))
    discovery.run_scan()
    return ResourceProjector(registry, discovery)


def test_same_internal_expose_port_not_conflict(store, registry) -> None:
    """两个容器都 expose 8097（内部端口）不构成主机端口冲突。"""
    proj = projector(
        store,
        registry,
        [
            container_payload(service="a", container_id="a" * 64, ports={"8097/tcp": None}),
            container_payload(service="b", container_id="b" * 64, ports={"8097/tcp": None}),
        ],
    )
    payload = proj.ports()
    assert len(payload["items"]) == 2
    assert payload["overlaps"] == []


def test_same_published_port_on_wildcard_and_specific_ip_overlaps(store, registry) -> None:
    proj = projector(
        store,
        registry,
        [
            container_payload(
                service="a",
                container_id="a" * 64,
                ports={"80/tcp": [{"HostIp": "0.0.0.0", "HostPort": "8080"}]},
            ),
            container_payload(
                service="b",
                container_id="b" * 64,
                ports={"80/tcp": [{"HostIp": "192.168.31.73", "HostPort": "8080"}]},
            ),
        ],
    )
    payload = proj.ports()
    assert len(payload["overlaps"]) == 1


def test_same_port_different_protocol_not_overlap() -> None:
    tcp = PortView(
        host_ip="0.0.0.0", host_port=9000, container_port=80, protocol="tcp", kind="published"
    )
    udp = PortView(
        host_ip="0.0.0.0", host_port=9000, container_port=80, protocol="udp", kind="published"
    )
    assert ports_overlap(tcp, udp) is False


def test_ipv6_wildcard_only_compared_within_ipv6() -> None:
    v6 = PortView(
        host_ip="::",
        host_port=443,
        container_port=443,
        address_family="ipv6",
        kind="published",
    )
    v4 = PortView(
        host_ip="0.0.0.0",
        host_port=443,
        container_port=443,
        address_family="ipv4",
        kind="published",
    )
    assert ports_overlap(v6, v4) is False
    v6_specific = PortView(
        host_ip="::1",
        host_port=443,
        container_port=443,
        address_family="ipv6",
        kind="published",
    )
    assert ports_overlap(v6, v6_specific) is True


def test_stopped_container_port_not_effective(store, registry) -> None:
    proj = projector(
        store,
        registry,
        [
            container_payload(
                service="live",
                container_id="a" * 64,
                ports={"80/tcp": [{"HostIp": "0.0.0.0", "HostPort": "8080"}]},
            ),
            container_payload(
                service="dead",
                container_id="b" * 64,
                state="exited",
                ports={"80/tcp": [{"HostIp": "0.0.0.0", "HostPort": "8080"}]},
            ),
        ],
    )
    payload = proj.ports()
    kinds = {row["kind"] for row in payload["items"]}
    assert kinds == {"published", "historical"}
    assert payload["overlaps"] == []


def test_host_network_component_has_no_ports(store, registry) -> None:
    proj = projector(
        store,
        registry,
        [
            container_payload(
                service="ha",
                container_id="a" * 64,
                network_mode="host",
                ports={"8123/tcp": [{"HostIp": "0.0.0.0", "HostPort": "8123"}]},
            )
        ],
    )
    payload = proj.ports()
    assert payload["items"] == []
    assert "不能据此证明端口空闲" in payload["scope_note"]


def test_ports_include_unregistered_components(store, registry) -> None:
    proj = projector(
        store,
        registry,
        [
            container_payload(
                service="loose",
                container_id="a" * 64,
                ports={"80/tcp": [{"HostIp": "0.0.0.0", "HostPort": "9999"}]},
            )
        ],
    )
    all_ports = proj.ports()
    registered_only = proj.ports(only_registered=True)
    assert len(all_ports["items"]) >= 1
    assert registered_only["items"] == []


def test_manual_port_note_marked_manual(store, registry) -> None:
    proj = projector(store, registry, [])
    service = registry.create_service(ServiceCreate(name="a"))
    registry.add_port_note(
        service.id, PortNoteInput(host_ip="0.0.0.0", host_port=3011, note="残留端口")
    )
    payload = proj.ports()
    row = payload["items"][0]
    assert row["origin"] == "manual"
    assert row["source"] == "manual"
    assert row["note"] == "残留端口"


def test_domains_derived_from_endpoints(store, registry) -> None:
    proj = projector(store, registry, [])
    service = registry.create_service(ServiceCreate(name="dividend"))
    registry.add_endpoint(
        service.id,
        EndpointInput(
            url="https://web.duomi77.cn:9443/dividend",
            label="web",
            kind="external",
        ),
    )
    registry.add_endpoint(
        service.id,
        EndpointInput(
            url="https://web.duomi77.cn:9443/index-trends",
            label="trends",
            kind="external",
        ),
    )
    payload = proj.domains()
    assert len(payload["items"]) == 2
    hosts = {row["host"] for row in payload["items"]}
    assert hosts == {"web.duomi77.cn"}
    ports = {row["port"] for row in payload["items"]}
    assert ports == {9443}
    assert all(row["is_ip"] is False for row in payload["items"])


def test_domains_expose_route_target(store, registry) -> None:
    proj = projector(store, registry, [])
    service = registry.create_service(ServiceCreate(name="a"))
    registry.add_endpoint(
        service.id,
        EndpointInput(
            url="https://web.duomi77.cn:9443/a",
            route_target=RouteTarget(
                component_source_key="nas:compose:personal-web:a:1",
                scheme="http",
                host="a-frontend",
                port=3003,
                path_prefix="/a",
            ),
        ),
    )
    row = proj.domains()["items"][0]
    assert row["route_target"]["host"] == "a-frontend"
    assert row["route_target"]["port"] == 3003


def test_ip_entry_flagged_as_ip(store, registry) -> None:
    proj = projector(store, registry, [])
    service = registry.create_service(ServiceCreate(name="a"))
    registry.add_endpoint(
        service.id, EndpointInput(url="http://192.168.31.73:8097/api/health")
    )
    row = proj.domains()["items"][0]
    assert row["is_ip"] is True


def test_certificates_dedup_by_host_and_port(store, registry) -> None:
    proj = projector(store, registry, [])
    service = registry.create_service(ServiceCreate(name="a"))
    for path in ("/a", "/b", "/c"):
        registry.add_endpoint(
            service.id, EndpointInput(url=f"https://web.duomi77.cn:9443{path}")
        )
    rows = proj.certificates()["items"]
    assert len(rows) == 1
    assert rows[0]["port"] == 9443
    assert len(rows[0]["used_by"]) == 3


def test_certificates_split_by_port(store, registry) -> None:
    proj = projector(store, registry, [])
    service = registry.create_service(ServiceCreate(name="a"))
    registry.add_endpoint(service.id, EndpointInput(url="https://a.duomi77.cn:12443/"))
    registry.add_endpoint(service.id, EndpointInput(url="https://a.duomi77.cn:9443/"))
    rows = proj.certificates()["items"]
    assert len(rows) == 2
    assert {row["port"] for row in rows} == {12443, 9443}


def test_http_endpoints_excluded_from_certificates(store, registry) -> None:
    proj = projector(store, registry, [])
    service = registry.create_service(ServiceCreate(name="a"))
    registry.add_endpoint(service.id, EndpointInput(url="http://192.168.31.73:8097/"))
    assert proj.certificates()["items"] == []


def test_binding_covers_rules() -> None:
    assert binding_covers("0.0.0.0", "192.168.31.73") is True
    assert binding_covers("192.168.31.73", "0.0.0.0") is False
    assert binding_covers("::", "fe80::1") is True
    assert binding_covers("", "10.0.0.1") is True
    assert binding_covers("10.0.0.1", "10.0.0.2") is False
