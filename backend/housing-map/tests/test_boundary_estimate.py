import json

import pytest
from shapely.geometry import Polygon

import scripts.estimate_boundaries as est
import src.services.boundary_estimate as svc

# 滨江某点(约)的 WGS84 坐标
WGS = (120.15, 30.18)


def _way(el_id, coords, name=None, landuse=False):
    tags = {}
    if name:
        tags["name"] = name
    if landuse:
        tags["landuse"] = "residential"
    return {"type": "way", "id": el_id, "tags": tags,
            "geometry": [{"lat": lat, "lon": lng} for lng, lat in coords]}


def _box(cx, cy, size=0.0004):
    """以 (cx, cy) 为中心的正方形楼面(WGS84 度)。size=0.0004° ≈ 40m。"""
    half = size / 2
    return [(cx - half, cy - half), (cx + half, cy - half), (cx + half, cy + half), (cx - half, cy + half)]


def test_gcj02_roundtrip():
    for lng, lat in [(120.15, 30.18), (120.211, 30.224), (119.99, 30.05)]:
        glng, glat = est.wgs84_to_gcj02(lng, lat)
        assert (glng, glat) != (lng, lat)  # 杭州域内必有偏移
        back = est.gcj02_to_wgs84(glng, glat)
        assert abs(back[0] - lng) < 1e-5
        assert abs(back[1] - lat) < 1e-5


def test_select_prefers_named_and_filters_distance():
    near = _box(WGS[0] + 0.0005, WGS[1])
    far = _box(WGS[0] + 0.004, WGS[1])          # ~370m 外
    named_far = _box(WGS[0] + 0.005, WGS[1])    # 更远但名字命中
    elements = [_way(1, near), _way(2, far), _way(3, named_far, name="钱塘山水")]
    center_in_near = (WGS[0] + 0.0005, WGS[1])  # 定位点在 near 楼内
    members, low = est.select_buildings(elements, center_in_near, "钱塘山水")
    assert not low
    assert Polygon(near) in members
    assert Polygon(named_far) in members
    assert Polygon(far) not in members


def test_select_clusters_by_gap_25m_and_40m():
    # 两栋楼间隙 25m → 同簇;第三栋距 40m → 异簇,取含定位点的簇
    deg25 = 25 / 111574.0
    deg40 = 40 / 111574.0
    base = WGS[0]
    a = _box(base, WGS[1])
    b = _box(base + 0.0004 + deg25, WGS[1])   # a 右边缘到 b 左边缘 ≈25m
    c = _box(base + 0.0004 + deg25 + 0.0004 + deg40, WGS[1])
    center_inside_a = (base, WGS[1])
    members, low = est.select_buildings([_way(1, a), _way(2, b), _way(3, c)], center_inside_a, None)
    assert Polygon(a) in members
    assert Polygon(b) in members
    assert Polygon(c) not in members
    assert not low


def test_select_low_confidence_when_point_outside_all():
    # 定位点在楼群旁的空地上(~160m,通过距离过滤但不含于任何簇):取最近簇并标 low_confidence
    lone = _box(WGS[0] + 0.0005, WGS[1] + 0.0015)
    members, low = est.select_buildings([_way(1, lone)], WGS, None)
    assert low
    assert Polygon(lone) in members


def test_build_boundary_contains_members_and_converts_to_gcj():
    a = _box(WGS[0], WGS[1])
    b = _box(WGS[0] + 0.0005, WGS[1])
    members = [Polygon(a), Polygon(b)]
    ring, count = est.build_boundary(members)
    assert count == 2
    # 首尾闭合
    assert ring[0] == ring[-1]
    # GCJ02 相对 WGS84 有偏移(杭州域内 >0)
    assert ring[0][0] > WGS[0]
    # 包含全部楼(逐点反算回 WGS84 后判断)
    back = [est.gcj02_to_wgs84(lng, lat) for lng, lat in ring]
    container = Polygon(back)
    assert container.contains(Polygon(a).centroid)
    assert container.contains(Polygon(b).centroid)


def test_fetch_uses_cache_and_mirror_fallback(tmp_path, monkeypatch):
    cache = tmp_path / "c1.json"
    calls = []

    def ok_fetcher(url, body):
        calls.append(url)
        return [_way(1, _box(*WGS))]

    first = est.fetch_elements(*WGS, cache, interval=0, fetcher=ok_fetcher)
    assert first and calls == [est.MIRRORS[0]]
    # 缓存命中:不再发请求
    second = est.fetch_elements(*WGS, cache, interval=0, fetcher=ok_fetcher)
    assert second == first
    assert len(calls) == 1

    # 主镜像挂 -> 第二镜像接管
    cache2 = tmp_path / "c2.json"

    def flaky(url, body):
        calls.append(url)
        if "overpass-api.de" in url:
            raise RuntimeError("406")
        return [_way(1, _box(*WGS))]

    est.fetch_elements(*WGS, cache2, interval=0, fetcher=flaky)
    assert "overpass-api.de" in calls[-2] and "kumi" in calls[-1]


def test_area_ha_sanity():
    ring = _box(WGS[0], WGS[1], size=0.001)  # ~100m 方块 ≈ 1 公顷
    ring.append(ring[0])
    ha = est._area_ha(ring)
    assert 0.7 < ha < 1.4


class FakeClock:
    """可推进的假时钟,用来验证总预算。"""

    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def test_fetch_stops_at_total_budget(tmp_path):
    """预算耗尽即放弃,不再试下一个镜像。"""
    clock = FakeClock()
    calls = []

    def slow_fetcher(url, body):
        calls.append(url)
        clock.advance(150)
        raise RuntimeError("boom")

    with pytest.raises(est.EstimateError) as error:
        est.fetch_elements(*WGS, tmp_path / "c.json", interval=0, fetcher=slow_fetcher,
                           clock=clock, budget_seconds=240)
    assert error.value.code == "timeout"
    assert len(calls) == 2  # 第三次尝试前预算已耗尽,不再发请求


def test_fetch_caps_single_request_by_remaining_budget(tmp_path, monkeypatch):
    """单次请求超时不能超过剩余预算,否则一次请求就能把总预算撑爆。"""
    clock = FakeClock()
    seen = []

    def fake_http_post(url, body, timeout=None):
        seen.append(timeout)
        clock.advance(100)
        raise RuntimeError("boom")

    monkeypatch.setattr(svc, "_http_post", fake_http_post)  # 服务模块里的才是真正被调用的
    with pytest.raises(est.EstimateError):
        est.fetch_elements(*WGS, tmp_path / "c.json", interval=0, clock=clock, budget_seconds=240)
    assert seen == [60, 60, 40]  # 第三次只剩 40 秒预算,单次超时被压到 40


def test_estimate_one_skips_snapshot_when_cache_disabled(tmp_path):
    """用户点"重新获取建筑"时连本地快照也不用,必须真的联网取最新的。"""
    lng_wgs, lat_wgs = est.gcj02_to_wgs84(WGS[0], WGS[1])
    snapshot = tmp_path / "all.json"
    snapshot.write_text(json.dumps({"elements": [_way(1, _box(lng_wgs, lat_wgs))]}), encoding="utf-8")
    paths = {"all": snapshot, "buildings": None, "residential": None}
    target = est.EstimateTarget(community_id="c1", community_name="测试小区",
                                longitude=WGS[0], latitude=WGS[1])

    fetched = []

    def fetcher(url, body):
        fetched.append(url)
        return [_way(2, _box(lng_wgs + 0.0005, lat_wgs))]

    # 默认: 用本地快照, 不联网
    est.estimate_one(target, snapshot_paths=paths, cache_dir=tmp_path / "cache1", fetcher=fetcher)
    assert fetched == []

    # 显式重新获取: 绕开快照走联网
    est.estimate_one(target, snapshot_paths=paths, cache_dir=tmp_path / "cache2",
                     fetcher=fetcher, use_cache=False)
    assert len(fetched) == 1


def test_load_snapshot_filters_bbox(tmp_path, monkeypatch):
    # 旧快照覆盖范围 30.17-30.20 / 120.15-120.21,取范围内的点
    point = (120.17, 30.185)
    inside = _way(1, _box(*point), name="楼A")
    outside = _way(2, _box(point[0] + 0.05, point[1]), name="楼B")
    buildings = {"elements": [inside, outside]}
    residential = {"elements": []}
    bpath, rpath = tmp_path / "b.json", tmp_path / "r.json"
    bpath.write_text(json.dumps(buildings), encoding="utf-8")
    rpath.write_text(json.dumps(residential), encoding="utf-8")
    monkeypatch.setattr(est, "SNAPSHOT_BUILDINGS", bpath)
    monkeypatch.setattr(est, "SNAPSHOT_RESIDENTIAL", rpath)
    monkeypatch.setattr(est, "SNAPSHOT_ALL", tmp_path / "all-absent.json")  # 屏蔽真实全量快照
    elements, covered = est.load_snapshot(*point)
    assert covered is True
    assert [el["id"] for el in elements] == [1]
    # 快照缺文件 -> 未覆盖,交给在线
    monkeypatch.setattr(est, "SNAPSHOT_BUILDINGS", tmp_path / "none.json")
    assert est.load_snapshot(*point) == ([], False)


def test_load_snapshot_not_covered_outside_extent(tmp_path, monkeypatch):
    """快照文件存在但覆盖范围不含该点时不算覆盖,必须转在线补查。"""
    bpath = tmp_path / "b.json"
    bpath.write_text(json.dumps({"elements": []}), encoding="utf-8")
    monkeypatch.setattr(est, "SNAPSHOT_ALL", tmp_path / "all-absent.json")
    monkeypatch.setattr(est, "SNAPSHOT_BUILDINGS", bpath)
    monkeypatch.setattr(est, "SNAPSHOT_RESIDENTIAL", bpath)
    # 萧山闻堰一带,超出旧快照覆盖范围(30.17-30.20 / 120.15-120.21)
    elements, covered = est.load_snapshot(120.155, 30.137)
    assert covered is False
    assert elements == []
