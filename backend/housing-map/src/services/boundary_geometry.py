"""轮廓几何校验:生成与应用两端共用同一套硬校验。

旧批量导入接口只查"环至少 4 点且首尾闭合",这里补齐有限值、坐标范围、环闭合与
不同顶点、多边形有效性、全部落在业务围栏内、面积上限六项。
"""
import math

from shapely.geometry import Polygon

from src.core.boundary import is_in_scope

MAX_AREA_KM2 = 1.0  # 与旧导入接口一致:超过即疑似粘连邻区


def approx_area_km2(rings: list[list[list[float]]]) -> float:
    """按环内最长环估算面积(平方公里)。"""
    ring = max(rings, key=len)
    lat0 = sum(point[1] for point in ring) / len(ring)
    km_lat = 110.574
    km_lng = 111.320 * math.cos(math.radians(lat0))
    pts = [(point[0] * km_lng, point[1] * km_lat) for point in ring]
    doubled = 0.0
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        doubled += x1 * y2 - x2 * y1
    return abs(doubled) / 2


def validate_rings(rings) -> str | None:
    """校验 GCJ02 轮廓环;通过返回 None,否则返回拒绝原因。"""
    if not rings or not isinstance(rings, list):
        return "轮廓为空"
    for ring in rings:
        if not isinstance(ring, list) or len(ring) < 4:
            return "轮廓环至少需要 4 个点(含重复的闭合点)"
        if ring[0] != ring[-1]:
            return "轮廓环首尾未闭合"
        distinct = {tuple(point) for point in ring[:-1]}
        if len(distinct) < 3:
            return "轮廓环至少需要 3 个不重复的点"
        for point in ring:
            if not isinstance(point, (list, tuple)) or len(point) != 2:
                return "轮廓点格式错误"
            lng, lat = point
            if not isinstance(lng, (int, float)) or not isinstance(lat, (int, float)):
                return "轮廓点必须是数值"
            if isinstance(lng, bool) or isinstance(lat, bool):
                return "轮廓点必须是数值"
            if not (math.isfinite(lng) and math.isfinite(lat)):
                return "轮廓点存在非有限数值"
            if not (-180 <= lng <= 180 and -90 <= lat <= 90):
                return "轮廓点坐标超出合法范围"
            if not is_in_scope(lng, lat):
                return "轮廓超出滨江/萧山接壤围栏"
    for ring in rings:
        poly = Polygon(ring)
        if not poly.is_valid:
            poly = poly.buffer(0)
        if poly.is_empty or poly.area <= 0:
            return "轮廓不是有效的非空多边形"
    if approx_area_km2(rings) > MAX_AREA_KM2:
        return "轮廓面积超过 1 平方公里(疑似粘连邻区)"
    return None
