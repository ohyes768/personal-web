"""API 集成测试: health / communities / score / transit / refresh 状态

依赖 backend/housing-map/data/ 下的运行时数据文件（随服务分发）。
"""

from fastapi.testclient import TestClient

from src.main import app

client = TestClient(app)


def test_health_returns_ok():
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_communities_structure():
    resp = client.get("/api/communities")
    assert resp.status_code == 200
    body = resp.json()
    # 响应键与源 Next.js 完全一致
    assert set(body.keys()) == {"success", "data", "total", "source", "transit"}
    assert body["success"] is True
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


def test_communities_excludes_dirty_data():
    resp = client.get("/api/communities")
    data = resp.json()["data"]
    names = {c["community_name"] for c in data}
    # 路名伪小区与个案脏数据不返回
    assert "江南大道" not in names
    assert "新街镇北塘河" not in names
    # 水电片区 4 个 drop 成员合并掉, 只留 primary
    assert "453982238" not in {c["community_id"] for c in data}
    assert "453982737" in {c["community_id"] for c in data}


def test_score_single_community():
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


def test_score_single_not_found():
    resp = client.get("/api/score?id=nonexistent-id")
    assert resp.status_code == 200
    assert resp.json() == {"success": False, "error": "找不到指定的小区"}


def test_score_batch_sorted_desc():
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
    assert body["meta"]["boundary_points"] == 334
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
