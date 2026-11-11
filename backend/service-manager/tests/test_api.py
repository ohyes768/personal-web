"""API 集成测试（A1 / A13 / A14 的契约面）。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.main import build_app

ORIGIN = {"Origin": "http://localhost:3012"}


@pytest.fixture()
def client(settings):
    app = build_app(settings)
    with TestClient(app) as test_client:
        yield test_client


def login(client: TestClient) -> None:
    response = client.post("/api/auth/login", json={"password": "test-password"})
    assert response.status_code == 200


def test_health_is_public(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ledger_requires_auth(client: TestClient) -> None:
    for path in ("/api/services", "/api/summary", "/api/discovery", "/api/resources/ports"):
        response = client.get(path)
        assert response.status_code == 401
        assert response.json()["code"] == "unauthorized"


def test_login_rejects_wrong_password(client: TestClient) -> None:
    response = client.post("/api/auth/login", json={"password": "nope"})
    assert response.status_code == 401


def test_login_sets_cookie_and_session_reports_it(client: TestClient) -> None:
    login(client)
    response = client.get("/api/auth/session")
    assert response.json()["authenticated"] is True


def test_session_endpoint_without_cookie(client: TestClient) -> None:
    response = client.get("/api/auth/session")
    assert response.json()["authenticated"] is False


def test_tampered_cookie_rejected(client: TestClient) -> None:
    login(client)
    client.cookies.clear()
    client.cookies.set("sm_session", "forged.value.here", path="/api")
    assert client.get("/api/services").status_code == 401


def test_write_requires_origin_header(client: TestClient) -> None:
    login(client)
    response = client.post("/api/services", json={"name": "x"})
    assert response.status_code == 401
    assert "Origin" in response.json()["message"]


def test_write_accepts_same_origin_host(client: TestClient) -> None:
    """直连 IP/其他端口访问时，Origin==Host 也通过（不依赖 public_origin 写死）。"""
    login(client)
    response = client.post(
        "/api/services",
        json={"name": "same-origin"},
        headers={"Origin": "http://testserver", "Host": "testserver"},
    )
    assert response.status_code == 201


def test_write_rejects_foreign_origin(client: TestClient) -> None:
    login(client)
    response = client.post(
        "/api/services", json={"name": "x"}, headers={"Origin": "https://evil.example"}
    )
    assert response.status_code == 401


def test_create_and_read_service(client: TestClient) -> None:
    login(client)
    created = client.post(
        "/api/services", json={"name": "股息率", "tags": ["public"]}, headers=ORIGIN
    )
    assert created.status_code == 201
    body = created.json()
    assert body["revision"] == 1
    listed = client.get("/api/services").json()
    assert listed["total"] == 1
    assert listed["items"][0]["status"]["runtime"] == "unknown"
    detail = client.get(f"/api/services/{body['id']}")
    assert detail.status_code == 200


def test_patch_conflict_returns_409(client: TestClient) -> None:
    login(client)
    created = client.post("/api/services", json={"name": "a"}, headers=ORIGIN).json()
    first = client.patch(
        f"/api/services/{created['id']}", json={"name": "b", "revision": 1}, headers=ORIGIN
    )
    assert first.status_code == 200
    second = client.patch(
        f"/api/services/{created['id']}", json={"name": "c", "revision": 1}, headers=ORIGIN
    )
    assert second.status_code == 409
    assert second.json()["code"] == "revision_conflict"


def test_validation_error_shape(client: TestClient) -> None:
    login(client)
    response = client.post("/api/services", json={}, headers=ORIGIN)
    assert response.status_code == 400
    body = response.json()
    assert body["code"] == "invalid_request"
    assert "name" in body["field_errors"]


def test_delete_service_removes_ledger(client: TestClient) -> None:
    login(client)
    created = client.post("/api/services", json={"name": "a"}, headers=ORIGIN).json()
    assert client.delete(f"/api/services/{created['id']}", headers=ORIGIN).status_code == 200
    assert client.get(f"/api/services/{created['id']}").status_code == 404


def test_logout_clears_session(client: TestClient) -> None:
    login(client)
    assert client.post("/api/auth/logout", headers=ORIGIN).status_code == 200
    assert client.get("/api/services").status_code == 401


def test_docker_unavailable_does_not_block_ledger(client: TestClient) -> None:
    login(client)
    summary = client.get("/api/summary").json()
    assert summary["docker_available"] is False
    created = client.post("/api/services", json={"name": "offline"}, headers=ORIGIN)
    assert created.status_code == 201


def test_endpoint_crud(client: TestClient) -> None:
    login(client)
    service = client.post("/api/services", json={"name": "a"}, headers=ORIGIN).json()
    endpoint = client.post(
        f"/api/services/{service['id']}/endpoints",
        json={"url": "https://web.duomi77.cn:9443/dividend", "label": "web"},
        headers=ORIGIN,
    )
    assert endpoint.status_code == 201
    body = endpoint.json()
    assert body["kind"] == "external"
    deleted = client.delete(
        f"/api/services/{service['id']}/endpoints/{body['id']}", headers=ORIGIN
    )
    assert deleted.status_code == 200


def test_resources_ports_scope_note(client: TestClient) -> None:
    login(client)
    payload = client.get("/api/resources/ports").json()
    assert payload["items"] == []
    assert "不能据此证明端口空闲" in payload["scope_note"]


def test_backup_export_excludes_observability(client: TestClient) -> None:
    login(client)
    client.post("/api/services", json={"name": "a"}, headers=ORIGIN)
    payload = client.get("/api/backup/export").json()
    assert payload["schema_version"] == 1
    assert len(payload["services"]) == 1
    for forbidden in ("check_results", "refresh_jobs", "release_reads", "password"):
        assert forbidden not in payload


def test_backup_preview_and_restore_roundtrip(client: TestClient) -> None:
    login(client)
    created = client.post("/api/services", json={"name": "a"}, headers=ORIGIN).json()
    exported = client.get("/api/backup/export").json()
    import json as jsonlib

    raw = jsonlib.dumps(exported).encode()
    # 清空台账
    client.delete(f"/api/services/{created['id']}", headers=ORIGIN)
    assert client.get("/api/services").json()["total"] == 0

    preview = client.post(
        "/api/backup/preview",
        files={"file": ("backup.json", raw, "application/json")},
        headers=ORIGIN,
    )
    assert preview.status_code == 200
    meta = preview.json()
    assert meta["counts"]["services"] == 1
    restored = client.post(
        "/api/backup/restore",
        data={
            "digest": meta["digest"],
            "registry_revision": str(meta["registry_revision"]),
            "confirm": "true",
        },
        files={"file": ("backup.json", raw, "application/json")},
        headers=ORIGIN,
    )
    assert restored.status_code == 200
    assert client.get("/api/services").json()["total"] == 1


def test_restore_rejects_digest_mismatch(client: TestClient) -> None:
    login(client)
    client.post("/api/services", json={"name": "a"}, headers=ORIGIN)
    exported = client.get("/api/backup/export").json()
    import json as jsonlib

    raw = jsonlib.dumps(exported).encode()
    preview = client.post(
        "/api/backup/preview",
        files={"file": ("b.json", raw, "application/json")},
        headers=ORIGIN,
    ).json()
    response = client.post(
        "/api/backup/restore",
        data={
            "digest": "0" * 64,
            "registry_revision": str(preview["registry_revision"]),
            "confirm": "true",
        },
        files={"file": ("b.json", raw, "application/json")},
        headers=ORIGIN,
    )
    assert response.status_code == 409
    assert response.json()["code"] == "digest_mismatch"


def test_restore_rejects_unknown_schema(client: TestClient) -> None:
    login(client)
    raw = b'{"schema_version": 99, "services": []}'
    response = client.post(
        "/api/backup/preview",
        files={"file": ("b.json", raw, "application/json")},
        headers=ORIGIN,
    )
    assert response.status_code == 400
    assert response.json()["code"] == "unsupported_schema"
