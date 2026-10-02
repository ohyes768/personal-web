"""transit 模块测试: 边界裁剪几何 + 线路/站点组装"""

from src.core.boundary import BINJIANG_BOUNDARY, XIAOSHAN_BORDER_BOUNDARIES, is_in_scope
from src.services.transit import build_subway_data, clip_to_scope, seg_boundary_intersect

P_INSIDE = [120.18, 30.18]
P_INSIDE2 = [120.19, 30.19]
# 西南方向远点 (富阳方向): 与滨江的连线不穿萧山板块, 保持"简单跨界"几何语义。
# (东北方向的远点会先穿过盈丰板块, 交点不再落在滨江边界上。)
P_OUTSIDE_FAR = [119.60, 30.00]


# ---------------------------------------------------------------------------
# segBoundaryIntersect
# ---------------------------------------------------------------------------

def test_seg_intersect_same_side_returns_none():
    assert seg_boundary_intersect(*P_INSIDE, *P_INSIDE2) is None
    assert seg_boundary_intersect(*P_OUTSIDE_FAR, 121.1, 30.6) is None


def test_seg_intersect_crossing_returns_point_near_boundary():
    cut = seg_boundary_intersect(*P_INSIDE, *P_OUTSIDE_FAR)
    assert cut is not None
    # 交点应非常接近边界上的某个顶点 (二分 16 次 ≈ 1 米级精度)
    min_dist = min(
        ((cut[0] - v[0]) ** 2 + (cut[1] - v[1]) ** 2) ** 0.5
        for v in BINJIANG_BOUNDARY
    )
    assert min_dist < 0.01  # ~1km 内必擦到边界 (宽松下限防抖动)


def test_seg_intersect_crossing_into_yingfeng():
    # 滨江 -> 东北远点: 直线依次穿过 滨江→盈丰→宁围 后出界 (板块间存在抽稀贴缝,
    # 二分定位到哪条边界取决于路径), 交点必须落在任一围栏顶点附近
    cut = seg_boundary_intersect(120.19, 30.20, 121.00, 30.50)
    assert cut is not None
    all_vertices = [
        *BINJIANG_BOUNDARY,
        *XIAOSHAN_BORDER_BOUNDARIES["闻堰"],
        *XIAOSHAN_BORDER_BOUNDARIES["宁围"],
        *XIAOSHAN_BORDER_BOUNDARIES["盈丰"],
    ]
    min_dist = min(
        ((cut[0] - v[0]) ** 2 + (cut[1] - v[1]) ** 2) ** 0.5
        for v in all_vertices
    )
    assert min_dist < 0.01


# ---------------------------------------------------------------------------
# clipToBinjiang
# ---------------------------------------------------------------------------

def test_clip_short_input_returns_empty():
    assert clip_to_scope([]) == []
    assert clip_to_scope([P_INSIDE]) == []


def test_clip_all_inside_kept_verbatim():
    coords = [P_INSIDE, P_INSIDE2, [120.195, 30.195]]
    assert clip_to_scope(coords) == [coords]


def test_clip_all_outside_dropped():
    coords = [P_OUTSIDE_FAR, [121.1, 30.6], [121.2, 30.7]]
    assert clip_to_scope(coords) == []


def test_clip_in_to_out_cuts_at_boundary():
    segments = clip_to_scope([P_INSIDE, P_OUTSIDE_FAR])
    assert len(segments) == 1
    seg = segments[0]
    assert seg[0] == P_INSIDE           # 起点保留
    assert seg[-1] != P_OUTSIDE_FAR     # 终点被截断
    assert len(seg) == 2


def test_clip_out_in_in_out_single_segment():
    # out -> in -> in -> out: 一次连续入区, 在进出边界处各截断一次 → 单段
    coords = [P_OUTSIDE_FAR, P_INSIDE, P_INSIDE2, P_OUTSIDE_FAR]
    segments = clip_to_scope(coords)
    assert len(segments) == 1
    seg = segments[0]
    assert seg[1] == P_INSIDE
    assert seg[2] == P_INSIDE2
    assert len(seg) == 4
    for pt in (seg[0], seg[3]):
        # 截断点在边界交点上 (不在区内, 距边界 < 0.01°)
        if not is_in_scope(pt[0], pt[1]):
            min_dist = min(
                ((pt[0] - v[0]) ** 2 + (pt[1] - v[1]) ** 2) ** 0.5
                for v in BINJIANG_BOUNDARY
            )
            assert min_dist < 0.01


def test_clip_out_in_out_in_out_two_segments():
    # out -> in -> out -> in -> out: 两段独立的入区段 → 2 段
    coords = [P_OUTSIDE_FAR, P_INSIDE, P_OUTSIDE_FAR, P_INSIDE, P_OUTSIDE_FAR]
    segments = clip_to_scope(coords)
    assert len(segments) == 2
    assert segments[0][1] == P_INSIDE
    assert segments[1][1] == P_INSIDE
    for seg in segments:
        assert len(seg) == 3
        for pt in seg:
            if not is_in_scope(pt[0], pt[1]):
                min_dist = min(
                    ((pt[0] - v[0]) ** 2 + (pt[1] - v[1]) ** 2) ** 0.5
                    for v in BINJIANG_BOUNDARY
                )
                assert min_dist < 0.01


# ---------------------------------------------------------------------------
# build_subway_data
# ---------------------------------------------------------------------------

def _route_feature(osm_id, route, coords):
    return {
        "type": "Feature",
        "properties": {"osm_id": osm_id, "route": route, "ref": "6", "name": "6号线", "colour": "#123456"},
        "geometry": {"type": "LineString", "coordinates": coords},
    }


def _stop_feature(osm_id, name, kind, lng, lat):
    return {
        "type": "Feature",
        "properties": {"osm_id": osm_id, "name": name, "kind": kind, "network": "杭州地铁"},
        "geometry": {"type": "Point", "coordinates": [lng, lat]},
    }


def test_build_subway_data_filters_and_clips():
    routes_geo = {"features": [
        _route_feature(111, "subway", [P_INSIDE, P_INSIDE2, P_OUTSIDE_FAR]),  # 地铁, 跨界
        _route_feature(222, "bus", [P_INSIDE, P_INSIDE2]),                   # 公交, 不参与
        _route_feature(333, "subway", [P_OUTSIDE_FAR, [121.1, 30.6]]),       # 地铁, 全在界外
    ]}
    stops_geo = {"features": [
        _stop_feature(1, "界内站", "subway", 120.18, 30.18),
        _stop_feature(2, "界外站", "subway", 121.00, 30.50),
        _stop_feature(3, "公交站", "bus", 120.18, 30.18),
    ]}

    routes, stops = build_subway_data(routes_geo, stops_geo)

    # 只有地铁 relation 333 被丢弃; 111 裁剪出 1 段
    assert len(routes) == 1
    assert routes[0]["id"] == "111-0"
    assert routes[0]["ref"] == "6"
    assert routes[0]["name"] == "6号线"
    assert routes[0]["colour"] == "#123456"
    assert routes[0]["path"][0] == P_INSIDE
    assert routes[0]["path"][-1] != P_OUTSIDE_FAR

    # 站点: kind=subway 且坐标在滨江内
    assert stops == [{"name": "界内站", "lng": 120.18, "lat": 30.18}]


def test_build_subway_data_null_input():
    routes, stops = build_subway_data(None, None)
    assert routes == []
    assert stops == []


# ---------------------------------------------------------------------------
# 萧山接壤板块 (盈丰/宁围/闻堰) — 2026-10 围栏扩展
# ---------------------------------------------------------------------------

P_YINGFENG = [120.25, 30.235]    # 盈丰 (钱江世纪城) 腹地
P_YINGFENG2 = [120.26, 30.245]
P_WENYAN = [120.19, 30.135]      # 闻堰腹地
P_XIAOSHAN_OUT = [120.27, 30.17]  # 萧山但板块外 (萧山城区南部方向)


def test_clip_keeps_yingfeng_segment():
    # 线路穿过盈丰板块: 全在板块内的两点应整段保留
    coords = [P_YINGFENG, P_YINGFENG2]
    segments = clip_to_scope(coords)
    assert segments == [coords]


def test_clip_line_crossing_binjiang_between_plates():
    # 盈丰 -> 闻堰 直线穿过滨江腹地 (同属 scope), 应整段保留不断开
    coords = [P_YINGFENG, P_WENYAN]
    assert clip_to_scope(coords) == [coords]


def test_build_subway_data_keeps_xiaoshan_stops():
    routes_geo = {"features": [
        _route_feature(555, "subway", [P_YINGFENG, P_YINGFENG2]),  # 盈丰板块内线路
    ]}
    stops_geo = {"features": [
        _stop_feature(9, "世纪城站", "subway", *P_YINGFENG),        # 盈丰内
        _stop_feature(10, "闻堰站", "subway", *P_WENYAN),           # 闻堰内
        _stop_feature(11, "板块外站", "subway", *P_XIAOSHAN_OUT),   # 萧山但板块外, 滤掉
    ]}
    routes, stops = build_subway_data(routes_geo, stops_geo)
    assert len(routes) == 1
    assert {s["name"] for s in stops} == {"世纪城站", "闻堰站"}
