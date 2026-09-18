"""地铁线路几何裁剪

移植自源项目 web/src/app/api/transit/route.ts (L49-153)。
多段线裁剪到滨江区边界内: in-out 交替处在交点断开, 输出边界内连续子段。
"""

from src.core.boundary import BINJIANG_BOUNDARY, is_in_binjiang


def seg_boundary_intersect(
    x1: float, y1: float, x2: float, y2: float
) -> list[float] | None:
    """路径与多边形边的交点 (lng,lat)。

    线段参数方程二分求解, 仅当两端一内一外时才计算, 排除端点恰在内的情况。
    """
    inside1 = is_in_binjiang(x1, y1)
    inside2 = is_in_binjiang(x2, y2)
    if inside1 == inside2:
        return None

    # 二分 16 次足够 (1e-5 度 ≈ 1 米, 单段最长 ~几十公里)
    lo, hi = 0.0, 1.0
    for _ in range(16):
        mid = (lo + hi) / 2
        mx = x1 + (x2 - x1) * mid
        my = y1 + (y2 - y1) * mid
        if is_in_binjiang(mx, my) == inside1:
            lo = mid
        else:
            hi = mid
    t = (lo + hi) / 2
    return [x1 + (x2 - x1) * t, y1 + (y2 - y1) * t]


def clip_to_binjiang(coords: list) -> list:
    """把多段线裁剪到滨江区边界内: 输出每一段在边界内的连续子段。

    (in-out-in-out... 交替时, 每次切换都在交点处断开)
    整段都在边界内 -> 整段保留; 整段都在边界外 -> 丢弃。
    """
    if len(coords) < 2:
        return []
    segments: list[list] = []
    current: list | None = None
    prev_inside = is_in_binjiang(coords[0][0], coords[0][1])
    if prev_inside:
        current = [[coords[0][0], coords[0][1]]]

    for i in range(1, len(coords)):
        x1, y1 = coords[i - 1][0], coords[i - 1][1]
        x2, y2 = coords[i][0], coords[i][1]
        inside = is_in_binjiang(x2, y2)

        if prev_inside and inside:
            # in -> in: 直接延伸
            current.append([x2, y2])
        elif not prev_inside and not inside:
            # out -> out: 跳过
            pass
        elif prev_inside and not inside:
            # in -> out: 在交点截断当前段
            cut = seg_boundary_intersect(x1, y1, x2, y2)
            if cut:
                current.append(cut)
            segments.append(current)
            current = None
        else:
            # out -> in: 起始交点起新段
            cut = seg_boundary_intersect(x1, y1, x2, y2)
            current = [cut, [x2, y2]] if cut else [[x2, y2]]
        prev_inside = inside

    # 处理端点恰在边界外导致 current 仍非空的情况
    if current is not None and len(current) >= 2:
        segments.append(current)
    return segments


def build_subway_data(
    routes_geo: dict | None, stops_geo: dict | None
) -> tuple[list[dict], list[dict]]:
    """从 transit GeoJSON 组装裁剪后的线路与站点数据

    线路: 只取 route === 'subway' 的 relation, 几何截断后展成多条子段
          (id = "<osm_id>-<idx>", 过境线进出滨江各一次会裁成 1~2 段)。
    站点: kind === 'subway' 且坐标严格在滨江内 (站名标错位置会误导)。
    """
    routes = (routes_geo or {}).get("features") or []
    stops = (stops_geo or {}).get("features") or []

    subway_routes: list[dict] = []
    for f in routes:
        props = f.get("properties") or {}
        if props.get("route") != "subway":
            continue
        clips = clip_to_binjiang((f.get("geometry") or {}).get("coordinates") or [])
        if len(clips) == 0:  # 完全在边界外
            continue
        for idx, clip in enumerate(clips):
            subway_routes.append({
                "id": f"{props.get('osm_id')}-{idx}",
                "ref": props.get("ref"),
                "name": props.get("name"),
                "colour": props.get("colour"),
                "path": clip,
            })

    subway_stops: list[dict] = []
    for f in stops:
        props = f.get("properties") or {}
        if props.get("kind") != "subway":
            continue
        coordinates = (f.get("geometry") or {}).get("coordinates") or []
        if len(coordinates) < 2:
            continue
        lng, lat = coordinates[0], coordinates[1]
        if not is_in_binjiang(lng, lat):
            continue
        subway_stops.append({"name": props.get("name"), "lng": lng, "lat": lat})

    return subway_routes, subway_stops


def boundary_points() -> int:
    """边界点数 (meta 用, 与源 BINJIANG_BOUNDARY.length 一致)"""
    return len(BINJIANG_BOUNDARY)
