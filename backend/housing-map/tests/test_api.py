"""API 集成测试: health / communities / score / transit / refresh 状态

communities/score 用例通过 seeded_data_dir 在 tmp 目录自造最小数据集，不再依赖
data/ 快照的鲜活度：快照里的 registry 与 admission 契约演进脱节后在当前代码下
全部 not_admitted（生产行为正确，NAS 数据是运行时演化的），不适合再当集成
fixture。无 registry 时展示链走 load_communities 原始 JSON 回退路径。
transit / refresh 等用例继续使用随服务分发的 data/ 快照。
"""

import json

import pytest
from fastapi.testclient import TestClient

from src.main import app

client = TestClient(app)


@pytest.fixture()
def seeded_data_dir(tmp_path, monkeypatch):
    """无 registry 的最小数据集: 展示链走 raw JSON 回退，坐标满足错区防护与 is_in_scope。"""
    # 名称/id 取自真实脏数据回归锚点: 路名伪小区、个案脏数据、merge drop/primary
    communities = [
        {"community_id": "10001742", "community_name": "倾城之恋花园"},
        {"community_id": "20044031", "community_name": "万科璞悦湾"},
        {"community_id": "50019001", "community_name": "通策广场"},
        {"community_id": "50019002", "community_name": "逸天广场"},
        {"community_id": "50019003", "community_name": "江南大道"},
        {"community_id": "50019004", "community_name": "新街镇北塘河"},
        {"community_id": "453982238", "community_name": "西兴镇水电社区"},
        {"community_id": "453982737", "community_name": "水电社区"},
    ]
    coordinates = {
        c["community_id"]: {
            "longitude": 120.208265,
            "latitude": 30.199576,
            "formatted_address": "杭州市滨江区长河街道",
        }
        for c in communities
    }
    files = {
        "binjiang_communities.json": communities,
        "binjiang_coordinates.json": coordinates,
        "binjiang_pois.json": {},
        "property_types.json": {},
        "binjiang_polygons_merged.json": {},
        "community_ages.json": {},
        "community_attrs.json": {},
        "binjiang_transit_routes.geojson": {"type": "FeatureCollection", "features": []},
        "binjiang_transit_stops.geojson": {"type": "FeatureCollection", "features": []},
    }
    for name, payload in files.items():
        (tmp_path / name).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    # price_snapshots.jsonl 缺失 -> load_price_snapshots 返回空 dict，价格字段为 null

    import src.services.data_loader as data_loader

    monkeypatch.setattr(data_loader, "DATA_DIR", tmp_path)
    return tmp_path


def test_health_returns_ok():
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_boundary_rebuild_status_is_separate_from_price_refresh():
    resp = client.get("/api/boundaries/rebuild")

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["phase"] == "idle"
    assert body["data"]["running"] is False


def test_market_reference_endpoint_returns_listing_reference_snapshot():
    resp = client.get("/api/market-reference")

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["available"] is True
    assert body["data"]["price_kind"] == "listing_reference"
    assert body["data"]["source"]["captured_at"]


def test_communities_structure(seeded_data_dir):
    resp = client.get("/api/communities")
    assert resp.status_code == 200
    body = resp.json()
    # 响应键与源 Next.js 完全一致 (stats 为收录口径统计, 无 registry 时为 None)
    assert set(body.keys()) == {"success", "data", "total", "source", "transit", "stats"}
    assert body["success"] is True
    assert body["stats"] is None
    assert body["total"] > 0
    assert body["source"] in ("real", "mock")
    assert body["total"] == len(body["data"])

    first = body["data"][0]
    for key in (
        "community_id", "community_name", "district", "subdistrict", "address",
        "latitude", "longitude", "price", "pois", "score", "build_year",
        "parking_ratio", "property_fee", "far_ratio", "greening_rate", "nearest_subway",
    ):
        assert key in first, f"缺少字段 {key}"
    # price 口径字段
    assert set(first["price"].keys()) == {
        "listing_avg_price", "deal_avg_price", "listing_count", "deal_count", "snapshot_date",
    }
    # score 五字段
    assert set(first["score"].keys()) == {
        "total_score", "location_score", "product_score", "amenity_score", "market_score",
    }
    assert 0 <= first["score"]["total_score"] <= 100
    # transit 为原始 FeatureCollection
    assert "features" in body["transit"]["routes"]
    assert "features" in body["transit"]["stops"]


def test_communities_excludes_dirty_data(seeded_data_dir):
    resp = client.get("/api/communities")
    data = resp.json()["data"]
    names = {c["community_name"] for c in data}
    # 路名伪小区与个案脏数据不返回；商办类小区放行（展示差异交给前端类型筛选）
    assert "江南大道" not in names
    assert "新街镇北塘河" not in names
    assert "通策广场" in names
    # 回归锚点: 物业类型"其他"的逸天广场必须下发, 否则前端类型筛选永远看不到
    assert "逸天广场" in names
    # 水电片区 4 个 drop 成员合并掉, 只留 primary
    assert "453982238" not in {c["community_id"] for c in data}
    assert "453982737" in {c["community_id"] for c in data}


def test_communities_reports_admission_stats(tmp_path, monkeypatch):
    """收录口径统计: 收录总量 vs 通过上图门槛数量, 未上图按 map_status 细分。"""
    import src.services.data_loader as data_loader
    from src.services.community_directory import prepare_directory

    communities = [
        {"community_id": "100", "community_name": "有坐标小区", "district": "滨江", "address": "杭州市滨江区测试路1号"},
        {"community_id": "200", "community_name": "无坐标小区", "district": "滨江", "address": "杭州市滨江区测试路2号"},
    ]
    coordinates = {
        # 坐标取自 admission API 测试同款围栏内点位
        "100": {"longitude": 120.207490, "latitude": 30.202261, "formatted_address": "杭州市滨江区测试路1号"},
    }
    (tmp_path / "binjiang_communities.json").write_text(json.dumps(communities, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "binjiang_coordinates.json").write_text(json.dumps(coordinates, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "property_types.json").write_text(json.dumps({
        "100": {"property_type": "住宅"}, "200": {"property_type": "住宅"}}), encoding="utf-8")
    for name, payload in {
        "binjiang_pois.json": {},
        "binjiang_polygons_merged.json": {},
        "community_ages.json": {},
        "community_attrs.json": {},
        "binjiang_transit_routes.geojson": {"type": "FeatureCollection", "features": []},
        "binjiang_transit_stops.geojson": {"type": "FeatureCollection", "features": []},
    }.items():
        (tmp_path / name).write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(data_loader, "DATA_DIR", tmp_path)
    prepare_directory(tmp_path)

    resp = client.get("/api/communities")
    body = resp.json()
    # 两个小区迁移后都被收录; 无坐标小区不上图并按原因细分
    assert body["stats"] == {"admitted": 2, "displayed": 1, "hidden": {"missing_coordinates": 1}}
    assert [c["community_name"] for c in body["data"]] == ["有坐标小区"]


def test_score_single_community(seeded_data_dir):
    resp = client.get("/api/communities")
    first_id = resp.json()["data"][0]["community_id"]

    resp = client.get(f"/api/score?id={first_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    # 单小区模式: listing_count/deal_count 固定 null, 无 boundary/property_type
    assert body["data"]["community_id"] == first_id
    assert body["data"]["price"]["listing_count"] is None
    assert body["data"]["price"]["deal_count"] is None
    assert "boundary" not in body["data"]
    assert "property_type" not in body["data"]


def test_score_single_not_found(seeded_data_dir):
    resp = client.get("/api/score?id=nonexistent-id")
    assert resp.status_code == 200
    assert resp.json() == {"success": False, "error": "找不到指定的小区"}


def test_score_batch_sorted_desc(seeded_data_dir):
    resp = client.get("/api/score?locationWeight=30&amenityWeight=30&productWeight=25&marketWeight=15")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["total"] == len(body["data"])
    assert body["weights"] == {"location": 30, "amenity": 30, "product": 25, "market": 15}
    scores = [c["score"]["total_score"] for c in body["data"]]
    assert scores == sorted(scores, reverse=True)


def test_transit_meta_and_structure():
    resp = client.get("/api/transit")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert set(body["meta"].keys()) == {"route_count", "stop_count", "boundary_points"}
    # 滨江 334 + 闻堰 200 + 宁围 100 + 盈丰 34 (2026-10 双围栏扩展)
    assert body["meta"]["boundary_points"] == 668
    assert body["meta"]["route_count"] > 0
    assert body["meta"]["stop_count"] > 0
    # 线路已几何截断: 每段至少 2 点, 节点不出滨江 bbox 太远
    route = body["data"]["routes"][0]
    assert set(route.keys()) == {"id", "ref", "name", "colour", "path"}
    assert len(route["path"]) >= 2
    stop = body["data"]["stops"][0]
    assert set(stop.keys()) == {"name", "lng", "lat"}


def test_transit_all_routes_have_id_suffix():
    resp = client.get("/api/transit")
    for route in resp.json()["data"]["routes"]:
        # id 形如 "<osm_id>-<idx>"
        osm_id, idx = route["id"].rsplit("-", 1)
        assert osm_id.isdigit() or len(osm_id) > 0
        assert idx.isdigit()


def test_refresh_status_initial_idle():
    resp = client.get("/api/refresh")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    job = body["data"]
    assert set(job.keys()) == {
        "running", "phase", "total", "processed", "okCount", "errorCount",
        "startedAt", "finishedAt", "error", "result",
    }
    assert job["running"] is False
    assert job["phase"] in ("idle", "fetching", "merging", "done", "error", "cancelled")
