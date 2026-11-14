"""主入口与证书：列表项带证书信息，主入口可按 URL upsert。

- 类型与是否查证书由后端按 URL 判定（规则只写一处）
- 列表项的证书状态来自最近一次 TLS 检查
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from src.main import build_app
from src.models import ServiceCreate
from src.registry import Registry

ORIGIN = {"Origin": "http://localhost:3012"}


@pytest.fixture()
def client(settings):
    app = build_app(settings)
    with TestClient(app) as test_client:
        yield test_client


def test_upsert_https_endpoint_is_external_and_checked(registry: Registry) -> None:
    service = registry.create_service(ServiceCreate(name="网站"))
    endpoint = registry.upsert_primary_endpoint(
        service.id, "https://web.duomi77.cn:9443/site"
    )
    assert endpoint.kind == "external"
    assert endpoint.tls_check is True
    assert endpoint.url == "https://web.duomi77.cn:9443/site"


def test_upsert_internal_address_is_internal_and_not_checked(registry: Registry) -> None:
    service = registry.create_service(ServiceCreate(name="内网"))
    endpoint = registry.upsert_primary_endpoint(service.id, "http://192.168.31.73:8010/")
    assert endpoint.kind == "internal"
    assert endpoint.tls_check is False


def test_upsert_updates_url_and_keeps_label(registry: Registry) -> None:
    service = registry.create_service(ServiceCreate(name="网站"))
    first = registry.upsert_primary_endpoint(service.id, "https://a.example.com/")
    # 手工补一个标签，第二次 upsert 不该把它抹掉
    registry.update_endpoint(service.id, first.id, first.model_copy(update={"label": "首页卡片入口"}))
    again = registry.upsert_primary_endpoint(service.id, "https://b.example.com/")
    assert again.url == "https://b.example.com/"
    assert again.label == "首页卡片入口"
    assert again.id == first.id


def test_list_item_carries_primary_endpoint_with_tls_state(
    registry: Registry, store
) -> None:
    service = registry.create_service(ServiceCreate(name="网站"))
    endpoint = registry.upsert_primary_endpoint(service.id, "https://web.duomi77.cn:9443/")
    # 塞一条 TLS 检查结果
    with store.transaction() as conn:
        conn.execute(
            "INSERT INTO check_results(target_type, target_id, check_kind, check_status,"
            " current_state, last_success_payload) VALUES ('endpoint', ?, 'tls', 'success',"
            " 'valid', ?)",
            (
                endpoint.id,
                json.dumps({"not_after": "2026-12-01T00:00:00+00:00", "days_remaining": 30}),
            ),
        )
    items, _ = registry.list_services()
    view = items[0].primary_endpoint
    assert view is not None
    assert view.url == "https://web.duomi77.cn:9443/"
    assert view.tls_state == "valid"
    assert view.tls_days_remaining == 30
    assert view.tls_not_after == "2026-12-01T00:00:00+00:00"


def test_list_item_without_endpoint_has_none(registry: Registry) -> None:
    registry.create_service(ServiceCreate(name="没有入口"))
    items, _ = registry.list_services()
    assert items[0].primary_endpoint is None


def test_api_upsert_primary_endpoint(client) -> None:
    client.post("/api/auth/login", json={"password": "test-password"})
    created = client.post(
        "/api/services", json={"name": "网站"}, headers=ORIGIN
    )
    assert created.status_code == 201
    service_id = created.json()["id"]

    response = client.put(
        f"/api/services/{service_id}/primary-endpoint",
        json={"url": "https://web.duomi77.cn:9443/site"},
        headers=ORIGIN,
    )
    assert response.status_code == 200
    assert response.json()["kind"] == "external"
    assert response.json()["tls_check"] is True

    listed = client.get("/api/services")
    endpoint = listed.json()["items"][0]["primary_endpoint"]
    assert endpoint["url"] == "https://web.duomi77.cn:9443/site"
    assert endpoint["tls_state"] == "unknown"
