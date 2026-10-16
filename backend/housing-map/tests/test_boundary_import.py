import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api import boundary_import_routes
from src.api.boundary_import_routes import router
from src.services.boundary_import import BACKUP_DIR, POLYGONS_PATH, rotate_backup

# 滨江范围内的一个三角环(首尾闭合,单位:度)
RING_IN = [
    [120.1900, 30.1900],
    [120.1920, 30.1900],
    [120.1910, 30.1920],
    [120.1900, 30.1900],
]
# 围栏外的环(远离滨江/萧山板块)
RING_OUT = [
    [121.9000, 30.9000],
    [121.9020, 30.9000],
    [121.9010, 30.9020],
    [121.9000, 30.9000],
]
# ~4km x 4km 的巨型环(触发面积上限)
RING_HUGE = [
    [120.17, 30.17],
    [120.21, 30.17],
    [120.21, 30.21],
    [120.17, 30.21],
    [120.17, 30.17],
]


@pytest.fixture()
def client(tmp_path, monkeypatch):
    polygons = tmp_path / "binjiang_polygons_merged.json"
    polygons.write_text(json.dumps({
        "_meta": {"description": "小区边界轮廓合并数据 (GCJ-02)", "sources": ["OpenStreetMap landuse=residential"], "matched": {"osm": 408}},
        "10000001": {"source": "osm", "rings": [RING_IN]},
    }, ensure_ascii=False), encoding="utf-8")
    backups = tmp_path / "backups"
    monkeypatch.setattr(boundary_import_routes, "load_display_communities",
                        lambda: [{"community_id": "10000001"}, {"community_id": "10000002"}])
    import src.services.boundary_import as svc
    monkeypatch.setattr(svc, "POLYGONS_PATH", polygons)
    monkeypatch.setattr(svc, "BACKUP_DIR", backups)
    monkeypatch.setenv("HOUSING_ADMIN_TOKEN", "secret-token")
    app = FastAPI()
    app.include_router(router, prefix="/api")
    return TestClient(app), polygons, backups


def _post(client, boundaries, token="secret-token", source="osm-building"):
    headers = {"X-Admin-Token": token} if token is not None else {}
    return client.post("/api/boundaries/import", json={"source": source, "boundaries": boundaries}, headers=headers)


def test_missing_token_returns_503(client, monkeypatch):
    http, *_ = client
    monkeypatch.delenv("HOUSING_ADMIN_TOKEN")
    resp = _post(http, [], token=None)
    assert resp.status_code == 503


def test_wrong_token_returns_401(client):
    http, *_ = client
    assert _post(http, [], token="wrong").status_code == 401
    assert _post(http, [], token=None).status_code == 401


def test_reject_unknown_community(client):
    http, polygons, _ = client
    item = {"community_id": "99999999", "coordinate_system": "gcj02", "rings": [RING_IN]}
    data = _post(http, [item]).json()["data"]
    assert data["accepted"] == []
    assert data["rejected"][0]["reason"] == "community_id 不在当前展示小区集合"
    assert "99999999" not in polygons.read_text(encoding="utf-8")


def test_reject_open_ring(client):
    http, *_ = client
    open_ring = RING_IN[:-1]
    item = {"community_id": "10000001", "coordinate_system": "gcj02", "rings": [open_ring]}
    data = _post(http, [item]).json()["data"]
    assert data["accepted"] == []
    assert "闭合" in data["rejected"][0]["reason"]


def test_reject_out_of_scope(client):
    http, *_ = client
    item = {"community_id": "10000001", "coordinate_system": "gcj02", "rings": [RING_OUT]}
    data = _post(http, [item]).json()["data"]
    assert data["accepted"] == []
    assert "围栏" in data["rejected"][0]["reason"]


def test_area_limit_unit():
    from src.api.boundary_import_routes import _approx_area_km2
    assert _approx_area_km2([RING_HUGE]) > 1.0
    assert _approx_area_km2([RING_IN]) < 0.1


def test_reject_wrong_source(client):
    http, *_ = client
    item = {"community_id": "10000001", "coordinate_system": "gcj02", "rings": [RING_IN]}
    resp = _post(http, [item], source="osm")
    assert resp.status_code == 422


def test_accept_writes_entry_with_meta_and_backup(client):
    http, polygons, backups = client
    meta = {"building_count": 14, "area_ha": 5.2}
    item = {"community_id": "10000002", "coordinate_system": "gcj02", "rings": [RING_IN], "meta": meta}
    data = _post(http, [item]).json()["data"]
    assert data["accepted"] == ["10000002"]
    assert data["rejected"] == []

    stored = json.loads(polygons.read_text(encoding="utf-8"))
    entry = stored["10000002"]
    assert entry["source"] == "osm-building"
    assert entry["rings"] == [RING_IN]
    assert entry["building_count"] == 14
    # 既有条目与 _meta 计数不被破坏
    assert stored["10000001"]["source"] == "osm"
    assert stored["_meta"]["matched"]["osm"] == 408
    assert stored["_meta"]["matched"]["osm-building"] == 1
    # 落盘前有备份
    assert list(backups.glob("binjiang_polygons_merged.*.json"))


def test_reupload_is_idempotent(client):
    http, polygons, _ = client
    item = {"community_id": "10000002", "coordinate_system": "gcj02", "rings": [RING_IN]}
    assert _post(http, [item]).status_code == 200
    assert _post(http, [item]).status_code == 200
    stored = json.loads(polygons.read_text(encoding="utf-8"))
    assert stored["_meta"]["matched"]["osm-building"] == 2  # 覆盖写,不累积条目
    assert [k for k in stored if k != "_meta"] == ["10000001", "10000002"]


def test_partial_accept_mixed_batch(client):
    http, polygons, _ = client
    good = {"community_id": "10000002", "coordinate_system": "gcj02", "rings": [RING_IN]}
    bad = {"community_id": "10000002", "coordinate_system": "gcj02", "rings": [RING_OUT]}
    data = _post(http, [good, bad]).json()["data"]
    assert data["accepted"] == ["10000002"]
    assert len(data["rejected"]) == 1
    stored = json.loads(polygons.read_text(encoding="utf-8"))
    assert stored["10000002"]["rings"] == [RING_IN]


def test_rotate_backup_keeps_recent_five(tmp_path):
    target = tmp_path / "poly.json"
    target.write_text("{}", encoding="utf-8")
    backup_dir = tmp_path / "backups"
    for _ in range(7):
        rotate_backup(target, backup_dir, keep=5)
    assert len(list(backup_dir.glob("poly.*.json"))) == 5
