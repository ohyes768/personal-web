import json
from pathlib import Path

import pytest
from shapely.geometry import Point, Polygon

import scripts.estimate_boundaries as est
import src.services.boundary_estimate as svc

FIXTURE = Path(__file__).parent / "fixtures" / "qiantang_daguan_osm.json"
SAMPLE_GCJ = (120.133258, 30.181901)
SAMPLE_WGS = (120.12850226078159, 30.1841956361507)

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


def _fixture_payload():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _fixture_elements():
    return _fixture_payload()["elements"]


def _write_snapshot(tmp_path, elements):
    path = tmp_path / "all.json"
    path.write_text(json.dumps({"elements": elements}, ensure_ascii=False), encoding="utf-8")
    return {"all": path, "buildings": None, "residential": None}


def _iou(ring_a, ring_b) -> float:
    left, right = Polygon(ring_a), Polygon(ring_b)
    if not left.is_valid:
        left = left.buffer(0)
    if not right.is_valid:
        right = right.buffer(0)
    union = left.union(right).area
    if union <= 0:
        return 0.0
    return left.intersection(right).area / union


def _converted_way_ring(way_id):
    element = next(el for el in _fixture_elements() if el["id"] == way_id)
    ring = []
    for point in element["geometry"]:
        lng, lat = svc.wgs84_to_gcj02(point["lon"], point["lat"])
        ring.append([round(lng, 6), round(lat, 6)])
    if ring[0] != ring[-1]:
        ring.append(ring[0])
    return ring


def test_fixture_keeps_target_and_neighbor():
    payload = _fixture_payload()
    ids = {el["id"] for el in payload["elements"]}
    assert 614214443 in ids
    assert 113467424 in ids
    named = {el["id"]: (el.get("tags") or {}).get("name") for el in payload["elements"]}
    assert named[614214443] == "观邸国际"
    assert named[113467424] == "贺田尚城"
    assert payload["meta"]["deduped"] is True


def test_identity_match_is_constrained_containment():
    assert svc.identity_match("观邸国际", ["观邸国际寓所"])
    assert svc.identity_match("观邸·国际", ["观邸 国际寓所"])
    assert not svc.identity_match("", ["观邸国际"])
    assert not svc.identity_match("观邸国际", [""])
    assert not svc.identity_match("观邸国际", ["国际"])
    assert not svc.identity_match("公寓", ["观邸国际寓所"])
    assert not svc.identity_match("钱塘大观", ["观邸国际"])


def test_aliases_from_source_does_not_guess():
    assert svc.aliases_from_source(None) == ()
    assert svc.aliases_from_source("") == ()
    assert svc.aliases_from_source("  ") == ()
    assert svc.aliases_from_source("观邸国际寓所") == ("观邸国际寓所",)


@pytest.mark.parametrize("osm_name,known", [
    ("长虹苑", "长虹苑"),
    ("朗庭", "朗庭"),
    ("彩虹城", "钱江彩虹城"),
    ("彩虹·城", "钱江彩虹城"),
])
def test_short_estate_names_can_match(osm_name, known):
    assert svc.identity_match(osm_name, [known])


@pytest.mark.parametrize("osm_name,known", [
    ("庭", "朗庭"),
    ("朗庭", "朗庭公寓"),
    ("公寓", "公寓"),
    ("住宅区", "住宅区"),
    ("小区", "某某小区"),
    ("长虹苑", "长虹南苑"),
])
def test_short_name_matching_does_not_accept_generic_or_partial_two_char_names(osm_name, known):
    assert not svc.identity_match(osm_name, [known])


@pytest.mark.parametrize("name,osm_name", [("长虹苑", "长虹苑"), ("钱江彩虹城", "彩虹城")])
def test_short_named_landuse_is_used_instead_of_a_single_building(name, osm_name):
    face = _box(*WGS, size=0.001)
    elements = [_way(1, face, name=osm_name, landuse=True), _way(2, _box(*WGS, size=0.0001))]
    result = svc.estimate_from_elements(elements, name=name, center_wgs=WGS)
    assert result.residential_faces == 1
    assert not result.low_confidence
    assert result.area_ha > 0.8
    assert svc.WARN_TRUSTED_LANDUSE in result.warnings


def test_short_named_landuse_still_requires_spatial_match():
    face = _box(WGS[0] + 0.01, WGS[1], size=0.001)
    members = svc.parse_members([_way(1, face, name="长虹苑", landuse=True)])
    from shapely.geometry import Point
    chosen, status = svc.choose_trusted_landuse(members, Point(WGS), ["长虹苑"])
    assert chosen is None
    assert status == "far"


@pytest.mark.parametrize("case_index", [0, 1])
def test_real_short_name_estates_use_existing_residential_faces(case_index):
    from pathlib import Path
    from shapely.geometry import Point
    payload = json.loads((Path(__file__).parent / "fixtures/short_name_landuse.json").read_text(encoding="utf-8"))
    case = payload["cases"][case_index]
    center = svc.gcj02_to_wgs84(case["longitude"], case["latitude"])
    result = svc.estimate_from_elements(case["elements"], name=case["name"], center_wgs=center)
    faces = [m for m in result.members if m.kind == "residential"]
    assert [m.element["id"] for m in faces] == [case["expected_osm_id"]]
    assert not result.low_confidence
    expected = Polygon(svc.member_ring_gcj02(faces[0]))
    actual = Polygon(result.ring)
    assert actual.covers(Point(case["longitude"], case["latitude"]))
    assert actual.intersection(expected).area / actual.union(expected).area >= 0.99


def test_short_name_conflicting_containing_faces_are_not_silently_chosen():
    from shapely.geometry import Point
    elements = [_way(1, _box(*WGS, size=0.001), name="长虹苑", landuse=True),
                _way(2, _box(*WGS, size=0.002), name="长虹苑", landuse=True)]
    chosen, status = svc.choose_trusted_landuse(svc.parse_members(elements), Point(WGS), ["长虹苑"])
    assert chosen is None
    assert status == "ambiguous"


def test_select_members_does_not_filter_by_foreign_landuse():
    point = (120.15, 30.18)
    target = _box(*point, 0.0003)
    neighbor = _box(point[0] + 0.0015, point[1], 0.0008)
    inside = _box(point[0] + 0.0015, point[1], 0.0002)
    elements = [
        _way(1, target),
        _way(2, neighbor, name="贺田尚城", landuse=True),
        _way(3, inside),
    ]
    members, low = est.select_buildings(elements, point, "钱塘大观")
    assert Polygon(target) in members
    assert Polygon(inside) not in members
    assert not low


def test_complex_residential_face_is_not_trusted():
    shell = _box(120.15, 30.18, size=0.002)
    hole = _box(120.15, 30.18, size=0.0005)
    poly = Polygon(shell, [hole])
    member = svc.Member(
        element={"type": "way", "id": 1, "tags": {"name": "观邸国际", "landuse": "residential"}},
        polygon=poly,
        kind="residential",
    )
    chosen, status = svc.choose_trusted_landuse(
        [member], Point(120.15, 30.18), ("钱塘大观", "观邸国际寓所"),
    )
    assert chosen is None
    assert status == "none"


def test_qiantang_sample_uses_matching_residential_face(tmp_path):
    paths = _write_snapshot(tmp_path, _fixture_elements())
    target = svc.EstimateTarget(
        community_id="20000561",
        community_name="钱塘大观",
        longitude=SAMPLE_GCJ[0],
        latitude=SAMPLE_GCJ[1],
        aliases=("观邸国际寓所",),
    )
    outcome = svc.estimate_one(target, snapshot_paths=paths, cache_dir=tmp_path / "cache")
    residential_ids = [m.element["id"] for m in outcome.members if m.kind == "residential"]
    assert residential_ids == [614214443]
    assert all(m.element["id"] != 113467424 for m in outcome.members)
    assert outcome.building_faces != 49
    assert not 8.2 <= outcome.area_ha <= 8.5
    assert Polygon(outcome.ring).covers(Point(SAMPLE_GCJ))
    reference = _converted_way_ring(614214443)
    reference_area = svc.area_ha(reference)
    candidate_area = svc.area_ha(outcome.ring)
    assert abs(candidate_area - reference_area) / reference_area <= 0.01
    assert _iou(outcome.ring, reference) >= 0.98
    assert any("采用名称匹配的住宅用地面外轮廓" in warning for warning in outcome.warnings)
    assert outcome.source == "osm-building"


def test_sample_without_alias_does_not_absorb_neighbor(tmp_path):
    paths = _write_snapshot(tmp_path, _fixture_elements())
    target = svc.EstimateTarget(
        community_id="20000561",
        community_name="钱塘大观",
        longitude=SAMPLE_GCJ[0],
        latitude=SAMPLE_GCJ[1],
        aliases=(),
    )
    outcome = svc.estimate_one(target, snapshot_paths=paths, cache_dir=tmp_path / "cache")
    assert all(m.element["id"] != 113467424 for m in outcome.members)
    assert outcome.residential_faces == 0
    assert outcome.building_faces != 49
    assert not 8.2 <= outcome.area_ha <= 8.5
    assert any("未匹配到可信住宅用地" in warning for warning in outcome.warnings)
    face = next(el for el in _fixture_elements() if el["id"] == 614214443)
    land = Polygon([(p["lon"], p["lat"]) for p in face["geometry"]])
    for member in outcome.members:
        geometry = member.element["geometry"]
        centroid = Polygon([(p["lon"], p["lat"]) for p in geometry]).centroid
        assert land.covers(centroid)


def test_residential_face_alone_still_succeeds(tmp_path):
    only = [el for el in _fixture_elements() if el["id"] == 614214443]
    paths = _write_snapshot(tmp_path, only)
    target = svc.EstimateTarget(
        community_id="20000561",
        community_name="钱塘大观",
        longitude=SAMPLE_GCJ[0],
        latitude=SAMPLE_GCJ[1],
        aliases=("观邸国际寓所",),
    )
    outcome = svc.estimate_one(target, snapshot_paths=paths, cache_dir=tmp_path / "cache")
    assert [m.element["id"] for m in outcome.members] == [614214443]
    assert outcome.building_faces == 0
    assert outcome.residential_faces == 1
    assert Polygon(outcome.ring).covers(Point(SAMPLE_GCJ))


def test_no_matching_face_keeps_building_cluster_with_warning():
    point = (120.15, 30.18)
    elements = [_way(1, _box(*point, 0.0003)), _way(2, _box(point[0] + 0.0004, point[1], 0.0003))]
    outcome = svc.estimate_from_elements(elements, name="钱塘大观", aliases=(), center_wgs=point)
    assert outcome.residential_faces == 0
    assert outcome.building_faces == 2
    assert any("未匹配到可信住宅用地" in warning for warning in outcome.warnings)


def test_differently_named_neighbor_is_not_absorbed():
    point = (120.15, 30.18)
    target = _box(*point, 0.0003)
    neighbor = _box(point[0] + 0.0015, point[1], 0.0008)
    extras = [_box(point[0] + 0.0015 + i * 0.00012, point[1], 0.00008) for i in range(-2, 3)]
    elements = [
        _way(1, target),
        _way(113467424, neighbor, name="贺田尚城", landuse=True),
        *[_way(10 + index, box) for index, box in enumerate(extras)],
    ]
    outcome = svc.estimate_from_elements(elements, name="钱塘大观", aliases=(), center_wgs=point)
    assert all(m.element["id"] != 113467424 for m in outcome.members)
    assert outcome.building_faces == 1
    assert any("未匹配到可信住宅用地" in warning for warning in outcome.warnings)


def test_same_name_far_away_is_not_a_silent_hit():
    point = (120.15, 30.18)
    gap = 200 / 110574.0
    size = 0.0006
    center_lat = point[1] + gap + size / 2
    face = _box(point[0], center_lat, size)
    building = _box(point[0], center_lat, 0.0002)
    elements = [
        _way(7, face, name="观邸国际", landuse=True),
        _way(8, building),
    ]
    with pytest.raises(svc.EstimateError) as error:
        svc.estimate_from_elements(
            elements, name="观邸国际寓所", aliases=(), center_wgs=point,
        )
    assert error.value.code == "no_geometry"
    assert "过远" in error.value.message


def test_multiple_matching_faces_warn_and_do_not_pick_the_larger():
    point = (120.15, 30.18)
    big = _box(*point, 0.002)
    small = _box(*point, 0.001)
    building = _box(*point, 0.0002)
    elements = [
        _way(1, big, name="观邸国际", landuse=True),
        _way(2, small, name="观邸国际寓所", landuse=True),
        _way(3, building),
    ]
    outcome = svc.estimate_from_elements(
        elements, name="钱塘大观", aliases=("观邸国际寓所",), center_wgs=point,
    )
    assert outcome.residential_faces == 0
    assert outcome.building_faces == 1
    assert any("无法区分" in warning for warning in outcome.warnings)


def test_unique_gate_within_150m_uses_the_face():
    point = (120.15, 30.18)
    gap = 80 / 110574.0
    size = 0.0008
    face = _box(point[0], point[1] + gap + size / 2, size)
    elements = [_way(9, face, name="观邸国际", landuse=True)]
    outcome = svc.estimate_from_elements(
        elements, name="观邸国际寓所", aliases=(), center_wgs=point,
    )
    assert [m.element["id"] for m in outcome.members if m.kind == "residential"] == [9]
    assert any("采用名称匹配的住宅用地面外轮廓" in warning for warning in outcome.warnings)


def test_empty_elements_raise_no_geometry():
    with pytest.raises(svc.EstimateError) as error:
        svc.estimate_from_elements([], name="钱塘大观", aliases=(), center_wgs=(120.15, 30.18))
    assert error.value.code == "no_geometry"


def test_cache_key_ignores_algorithm_version(monkeypatch):
    monkeypatch.setattr(svc, "ALGORITHM_VERSION", "v1")
    first = svc.cache_key("20000561", *SAMPLE_WGS)
    monkeypatch.setattr(svc, "ALGORITHM_VERSION", "v9")
    second = svc.cache_key("20000561", *SAMPLE_WGS)
    assert first == second


def test_cli_target_passes_existing_alias_only():
    local = est.build_estimate_target({
        "community_id": "20000561",
        "community_name": "钱塘大观",
        "community_alias": "观邸国际寓所",
        "longitude": SAMPLE_GCJ[0],
        "latitude": SAMPLE_GCJ[1],
    })
    remote = est.build_estimate_target({
        "community_id": "20000561",
        "community_name": "钱塘大观",
        "longitude": SAMPLE_GCJ[0],
        "latitude": SAMPLE_GCJ[1],
    })
    assert local.aliases == ("观邸国际寓所",)
    assert remote.aliases == ()


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
