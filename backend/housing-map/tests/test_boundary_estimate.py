import json

import pytest
from shapely.geometry import Polygon

import scripts.estimate_boundaries as est

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


def test_load_snapshot_filters_bbox(tmp_path, monkeypatch):
    inside = _way(1, _box(*WGS), name="楼A")
    outside = _way(2, _box(WGS[0] + 0.05, WGS[1]), name="楼B")
    buildings = {"elements": [inside, outside]}
    residential = {"elements": []}
    bpath, rpath = tmp_path / "b.json", tmp_path / "r.json"
    bpath.write_text(json.dumps(buildings), encoding="utf-8")
    rpath.write_text(json.dumps(residential), encoding="utf-8")
    monkeypatch.setattr(est, "SNAPSHOT_BUILDINGS", bpath)
    monkeypatch.setattr(est, "SNAPSHOT_RESIDENTIAL", rpath)
    monkeypatch.setattr(est, "SNAPSHOT_ALL", tmp_path / "all-absent.json")  # 屏蔽真实全量快照
    elements = est.load_snapshot(*WGS)
    assert [el["id"] for el in elements] == [1]
    # 快照缺文件 -> None(交给在线)
    monkeypatch.setattr(est, "SNAPSHOT_BUILDINGS", tmp_path / "none.json")
    assert est.load_snapshot(*WGS) is None
