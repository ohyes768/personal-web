"""单小区轮廓估算:OSM 建筑/住宅面聚类 → 外轮廓 → GCJ02 候选。

本模块是唯一算法实现处:
  - CLI  `scripts/estimate_boundaries.py` 批量预览与导出
  - 后台 `src/services/boundary_workflow.py` 单小区生成候选

坐标口径:输入小区坐标为 GCJ02,OSM 建筑为 WGS84,候选轮廓输出 GCJ02。
"""
from __future__ import annotations

import hashlib
import json
import math
import threading
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from shapely.geometry import Point, Polygon
from shapely.ops import unary_union

from src.services.data_loader import DATA_DIR

# 运行时快照与缓存(与 CLI 共用同一份,快照缺失时自动转在线)
SNAPSHOT_ALL = DATA_DIR / "binjiang_osm_buildings_all_raw.json"
SNAPSHOT_BUILDINGS = DATA_DIR / "binjiang_osm_named_buildings_raw.json"
SNAPSHOT_RESIDENTIAL = DATA_DIR / "binjiang_osm_residential_raw.json"
CACHE_DIR = DATA_DIR / "boundary_cache"

BBOX_DEG = 0.002          # 定位点 ±0.002° ≈ ±220m
MAX_CENTROID_M = 250.0    # 楼质心距定位点上限
CLUSTER_GAP_M = 15.0      # 楼面 buffer 半径,使 ≤30m 间隙粘连成簇
FILL_M = 20.0             # 合并后填缝半径
SIMPLIFY_DEG = 0.0001
REQUEST_INTERVAL = 10.0   # 服务内每次外网请求的最小间隔(秒)
REQUEST_TIMEOUT = 60.0    # 单次请求超时(秒)
TASK_BUDGET_SECONDS = 240.0  # 单任务联网总预算(秒)
CACHE_TTL_DAYS = 7
QUERY_VERSION = "v2"      # 查询语义变化时递增,顺带作废旧缓存
MIRRORS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]
USER_AGENT = "housing-map-boundary-estimate/1.0 (personal project)"

# 快照覆盖范围(bbox):全量快照覆盖滨江全域,旧的具名/住宅面快照只覆盖核心区。
SNAPSHOT_ALL_EXTENT = (30.10, 120.10, 30.26, 120.28)
SNAPSHOT_LEGACY_EXTENT = (30.17, 120.15, 30.20, 120.21)

# ---------------------------------------------------------------------------
# WGS84 <-> GCJ02(标准偏移算法,互逆用一次反射近似,误差 <1m)
# ---------------------------------------------------------------------------
_PI = math.pi
_A = 6378245.0
_EE = 0.00669342162296594323


def _out_of_china(lng, lat):
    return not (73.66 < lng < 135.05 and 3.86 < lat < 53.55)


def _offset(lng, lat):
    dlat = -100.0 + 2.0 * lng + 3.0 * lat + 0.2 * lat * lat + 0.1 * lng * lat + 0.2 * math.sqrt(abs(lng))
    dlat += (20.0 * math.sin(6.0 * lng * _PI) + 20.0 * math.sin(2.0 * lng * _PI)) * 2.0 / 3.0
    dlat += (20.0 * math.sin(lat * _PI) + 40.0 * math.sin(lat / 3.0 * _PI)) * 2.0 / 3.0
    dlat += (160.0 * math.sin(lat / 12.0 * _PI) + 320.0 * math.sin(lat * _PI / 30.0)) * 2.0 / 3.0
    dlng = 300.0 + lng + 2.0 * lat + 0.1 * lng * lng + 0.1 * lng * lat + 0.1 * math.sqrt(abs(lng))
    dlng += (20.0 * math.sin(6.0 * lng * _PI) + 20.0 * math.sin(2.0 * lng * _PI)) * 2.0 / 3.0
    dlng += (20.0 * math.sin(lat * _PI) + 40.0 * math.sin(lat / 3.0 * _PI)) * 2.0 / 3.0
    dlng += (150.0 * math.sin(lat / 12.0 * _PI) + 300.0 * math.sin(lat / 30.0)) * 2.0 / 3.0
    return dlat, dlng


def wgs84_to_gcj02(lng, lat):
    if _out_of_china(lng, lat):
        return lng, lat
    dlat, dlng = _offset(lng - 105.0, lat - 35.0)
    radlat = lat / 180.0 * _PI
    magic = 1 - _EE * math.sin(radlat) ** 2
    sqrtmagic = math.sqrt(magic)
    dlat = (dlat * 180.0) / ((_A * (1 - _EE)) / (magic * sqrtmagic) * _PI)
    dlng = (dlng * 180.0) / (_A / sqrtmagic * math.cos(radlat) * _PI)
    return lng + dlng, lat + dlat


def gcj02_to_wgs84(lng, lat, iterations=2):
    """迭代逼近逆变换(两次后残差 <1e-6°,远小于楼块尺度)。"""
    if _out_of_china(lng, lat):
        return lng, lat
    wlng, wlat = lng, lat
    for _ in range(iterations):
        glng, glat = wgs84_to_gcj02(wlng, wlat)
        wlng += lng - glng
        wlat += lat - glat
    return wlng, wlat


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Member:
    """参与聚类的一个 OSM 面。kind 区分建筑面与住宅用地面。"""
    element: dict
    polygon: Polygon
    kind: str  # 'building' | 'residential'


@dataclass(frozen=True)
class EstimateTarget:
    community_id: str
    community_name: str
    longitude: float  # GCJ02
    latitude: float   # GCJ02


@dataclass(frozen=True)
class EstimateOutcome:
    ring: list[list[float]]                 # GCJ02 闭合外环
    members: tuple[Member, ...]
    building_faces: int
    residential_faces: int
    dropped_parts: int                      # 合并后被舍弃的分簇数
    low_confidence: bool
    warnings: tuple[str, ...]
    area_ha: float
    source: str = "osm-building"


class EstimateError(RuntimeError):
    """估算失败。code 供前端区分错误类别。"""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


# ---------------------------------------------------------------------------
# 要素解析与楼群挑选
# ---------------------------------------------------------------------------

def _read_json(path, fallback):
    path = Path(path)
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _as_elements(data):
    """Overpass dump 兼容:{"elements": [...]} 或裸 [...]。"""
    if isinstance(data, dict):
        return data.get("elements") or []
    return data if isinstance(data, list) else []


def parse_members(elements) -> list[Member]:
    """elements -> 成员面列表,非法几何丢弃。"""
    members: list[Member] = []
    for el in elements:
        geometry = [g for g in (el.get("geometry") or []) if g]  # 跨界 way 的 out geom 可能含 null 点
        coords = [(g["lon"], g["lat"]) for g in geometry]
        if len(coords) < 3:
            continue
        try:
            poly = Polygon(coords)
        except (ValueError, TypeError):
            continue
        if not poly.is_valid:
            poly = poly.buffer(0)
        if poly.is_empty or poly.area <= 0:
            continue
        kind = "residential" if (el.get("tags") or {}).get("landuse") == "residential" else "building"
        members.append(Member(element=el, polygon=poly, kind=kind))
    return members


def _point_distance_m(point, poly):
    dlat = point.y - poly.centroid.y
    dlng = point.x - poly.centroid.x
    return math.hypot(dlat * 110574.0, dlng * 111320.0 * math.cos(math.radians(point.y)))


def _name_hit(el_name, community_name):
    """双向包含:楼名"倾城之恋3幢"与小区名"顺发倾城之恋"互为子串即命中。"""
    if not community_name or not el_name:
        return False
    return community_name in el_name or el_name in community_name


def select_members(elements, center_wgs, name) -> tuple[list[Member], bool]:
    """名称优先 + 距离过滤 + landuse 收编 + 连通聚簇;中心点须为 WGS84(与 OSM 同系)。

    名称命中的楼与具名 residential 面(小区边界本体)无条件入选;其余楼聚类后取含定位点的簇。
    返回 (成员面列表, low_confidence)。"""
    members = parse_members(elements)
    buildings = [m for m in members if m.kind == "building"]
    landuse = [m for m in members if m.kind == "residential"]
    point = Point(center_wgs)

    named = [m for m in buildings if _name_hit((m.element.get("tags") or {}).get("name"), name)]
    named_residential = [m for m in landuse if _name_hit((m.element.get("tags") or {}).get("name"), name)]
    rest = [m for m in buildings if not _name_hit((m.element.get("tags") or {}).get("name"), name)]
    rest = [m for m in rest if _point_distance_m(point, m.polygon) <= MAX_CENTROID_M]
    other_landuse = [m for m in landuse if m not in named_residential]
    if other_landuse:
        inside = [m for m in rest if any(m.polygon.within(lu.polygon) for lu in other_landuse)]
        if inside:
            rest = inside
    if not named and not named_residential and not rest:
        return [], True

    low_confidence = False
    cluster: list[Member] = []
    if rest:
        buf_deg = CLUSTER_GAP_M / 111574.0  # 近似 1m ≈ 1/111574°(滨江纬度下 ±5% 内)
        buffered = [m.polygon.buffer(buf_deg) for m in rest]
        merged = unary_union(buffered)
        parts = list(merged.geoms) if merged.geom_type == "MultiPolygon" else [merged]
        target = next((part for part in parts if part.covers(point) or part.distance(point) < 1e-6), None)
        if target is None:
            # 名称已给出可信成员时不降置信;仅裸聚类取最近簇时才标低置信
            low_confidence = not (named or named_residential)
            target = min(parts, key=lambda part: part.distance(point))
        cluster = [m for m, buf in zip(rest, buffered) if buf.intersects(target)]
    return named + named_residential + cluster, low_confidence


def select_buildings(elements, center_wgs, name) -> tuple[list[Polygon], bool]:
    """兼容旧调用:只返回成员面与低置信标记。"""
    members, low_confidence = select_members(elements, center_wgs, name)
    return [m.polygon for m in members], low_confidence


def _member_polygons(members) -> list[Polygon]:
    """成员项可以是 Member,也可以直接是 Polygon(兼容旧调用)。"""
    return [m.polygon if isinstance(m, Member) else m for m in members]


def build_boundary_detail(members) -> tuple[list[list[float]], int, int]:
    """成员面合并 → 填缝 → 最大外环 → 简化;外环逐点转 GCJ02。

    返回 (GCJ02 外环, 被舍弃的分簇数, 成员面总数)。"""
    polygons = _member_polygons(members)
    if not polygons:
        raise EstimateError("no_geometry", "没有可用于生成轮廓的建筑面")
    merged = unary_union(polygons)
    fill_deg = FILL_M / 111574.0
    filled = merged.buffer(fill_deg).buffer(-fill_deg)
    polys = list(filled.geoms) if filled.geom_type == "MultiPolygon" else [filled]
    biggest = max(polys, key=lambda poly: poly.area)
    ring = biggest.simplify(SIMPLIFY_DEG).exterior.coords[:]
    if len(ring) < 3:
        raise EstimateError("invalid_geometry", "合并后的轮廓顶点不足")
    gcj_ring = []
    for lng, lat in ring:
        glng, glat = wgs84_to_gcj02(lng, lat)
        gcj_ring.append([round(glng, 6), round(glat, 6)])
    return gcj_ring, len(polys) - 1, len(polygons)


def build_boundary(members):
    """兼容旧调用:返回 (GCJ02 外环, 成员面数量)。"""
    ring, _dropped, count = build_boundary_detail(members)
    return ring, count


def area_ha(ring) -> float:
    """环面积(公顷)。"""
    lat0 = sum(p[1] for p in ring) / len(ring)
    km_lat, km_lng = 110.574, 111.320 * math.cos(math.radians(lat0))
    pts = [(p[0] * km_lng, p[1] * km_lat) for p in ring]
    doubled = sum((x1 * y2 - x2 * y1) for (x1, y1), (x2, y2) in zip(pts, pts[1:]))
    return abs(doubled) / 2 * 100


def member_ring_gcj02(member: Member) -> list[list[float]]:
    """成员面外环转 GCJ02,供前端预览参考建筑。"""
    ring = []
    for lng, lat in member.polygon.exterior.coords:
        glng, glat = wgs84_to_gcj02(lng, lat)
        ring.append([round(glng, 6), round(glat, 6)])
    return ring


# ---------------------------------------------------------------------------
# 快照与 Overpass 抓取
# ---------------------------------------------------------------------------

def overpass_query(lng, lat):
    s, w, n, e = lat - BBOX_DEG, lng - BBOX_DEG, lat + BBOX_DEG, lng + BBOX_DEG
    return (
        f"[out:json][timeout:60];"
        f'(way["building"]({s},{w},{n},{e});'
        f'way["landuse"="residential"]({s},{w},{n},{e}););'
        f"out geom;"
    )


def _bbox_of(lng, lat):
    return (lat - BBOX_DEG, lng - BBOX_DEG, lat + BBOX_DEG, lng + BBOX_DEG)


def default_snapshot_paths() -> dict:
    """默认快照路径(调用时读取,便于测试替换)。"""
    return {"all": SNAPSHOT_ALL, "buildings": SNAPSHOT_BUILDINGS, "residential": SNAPSHOT_RESIDENTIAL}


def _covers(extent, bbox) -> bool:
    """extent 是否完全覆盖 bbox(南,西,北,东)。"""
    return (bbox[0] >= extent[0] and bbox[1] >= extent[1]
            and bbox[2] <= extent[2] and bbox[3] <= extent[3])


def load_snapshot(lng, lat, *, snapshot_all=None, snapshot_buildings=None, snapshot_residential=None):
    """本地快照取 bbox 内要素。

    返回 (elements, covered)。covered=False 表示快照存在但不覆盖该点,
    调用方应改走在线补查 —— 快照文件存在不等于该区域已采集。"""
    bbox = _bbox_of(lng, lat)
    if snapshot_all is not None and Path(snapshot_all).exists():
        if not _covers(SNAPSHOT_ALL_EXTENT, bbox):
            return [], False
        return _picked(_as_elements(_read_json(snapshot_all, {})), bbox), True
    if snapshot_buildings is None or snapshot_residential is None:
        return [], False
    if not (Path(snapshot_buildings).exists() and Path(snapshot_residential).exists()):
        return [], False
    if not _covers(SNAPSHOT_LEGACY_EXTENT, bbox):
        return [], False
    picked = []
    for path in (snapshot_buildings, snapshot_residential):
        picked.extend(_picked(_as_elements(_read_json(path, {})), bbox))
    return picked, True


def _picked(elements, bbox) -> list[dict]:
    s, w, n, e = bbox
    picked = []
    for el in elements:
        geometry = [g for g in (el.get("geometry") or []) if g]
        if not geometry:
            continue
        mid_lng = sum(g["lon"] for g in geometry) / len(geometry)
        mid_lat = sum(g["lat"] for g in geometry) / len(geometry)
        if w <= mid_lng <= e and s <= mid_lat <= n:
            picked.append({**el, "geometry": geometry})
    return picked


# 外网请求全局节奏:任意两次真实请求起始间隔不小于 REQUEST_INTERVAL。
_request_lock = threading.Lock()
_last_request_at = 0.0


def cache_key(community_id: str, lng_wgs: float, lat_wgs: float) -> str:
    """缓存键含查询 bbox 与查询版本,不能只按小区 ID。"""
    s, w, n, e = _bbox_of(lng_wgs, lat_wgs)
    payload = f"{QUERY_VERSION}|{community_id}|{s:.6f},{w:.6f},{n:.6f},{e:.6f}"
    digest = hashlib.sha256(payload.encode()).hexdigest()[:16]
    return f"{community_id}-{digest}"


def cache_path_for(cache_dir, community_id: str, lng_wgs: float, lat_wgs: float) -> Path:
    return Path(cache_dir) / f"{cache_key(community_id, lng_wgs, lat_wgs)}.json"


def fetch_elements(lng_wgs, lat_wgs, cache_path, interval=REQUEST_INTERVAL, fetcher=None,
                   *, clock=time.time, sleeper=time.sleep, timeout=REQUEST_TIMEOUT, use_cache=True):
    """带 7 天缓存与镜像 fallback 的 Overpass 抓取;返回 elements 列表。

    缓存内容记录查询 bbox 与版本,只有完全匹配才复用。use_cache=False 时忽略已有缓存
    强制重新抓取(用户显式选择"重新获取建筑")。"""
    cache_path = Path(cache_path)
    bbox = _bbox_of(lng_wgs, lat_wgs)
    if use_cache and cache_path.exists():
        age_days = (clock() - cache_path.stat().st_mtime) / 86400
        if age_days < CACHE_TTL_DAYS:
            payload = _read_json(cache_path, {})
            if (isinstance(payload, dict) and payload.get("version") == QUERY_VERSION
                    and payload.get("bbox") == [round(v, 6) for v in bbox]):
                return payload.get("elements") or []
    query = overpass_query(lng_wgs, lat_wgs)
    body = urllib.parse.urlencode({"data": query}).encode()
    errors = []
    do_fetch = fetcher or _http_post
    for mirror in MIRRORS:
        try:
            _pace(interval, clock, sleeper, injected=fetcher is not None)
            elements = do_fetch(mirror, body)
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(
                {"version": QUERY_VERSION, "bbox": [round(v, 6) for v in bbox], "elements": elements},
                ensure_ascii=False), encoding="utf-8")
            return elements
        except Exception as exc:  # noqa: BLE001 - 镜像逐个降级,任何失败都换下一个
            errors.append(f"{mirror}: {exc}")
    raise EstimateError("network", "所有 Overpass 镜像均失败:\n" + "\n".join(errors))


def _pace(interval, clock, sleeper, *, injected=False):
    """真实请求前等待到全局最小间隔;注入 fetcher 的测试不等待。"""
    global _last_request_at
    if injected or interval <= 0:
        return
    with _request_lock:
        now = clock()
        wait = interval - (now - _last_request_at)
        if wait > 0:
            sleeper(wait)
        _last_request_at = clock()


def _http_post(url, body):
    req = urllib.request.Request(url, data=body, headers={
        "User-Agent": USER_AGENT,
        "Content-Type": "application/x-www-form-urlencoded",
    })
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
        return json.load(resp)["elements"]


# ---------------------------------------------------------------------------
# 单小区估算
# ---------------------------------------------------------------------------

def estimate_one(target: EstimateTarget, *, snapshot_paths=None, cache_dir=None,
                 fetcher=None, progress=None, clock=time.time, sleeper=time.sleep,
                 use_cache=True) -> EstimateOutcome:
    """为一个小区生成候选轮廓。

    数据来源顺序:坐标匹配的本地快照 → 在线 Overpass。快照存在但不覆盖该点时
    仍走在线 —— 快照文件存在不等于该区域已采集。

    progress(phase, detail) 的 phase 取值:reading / fetching / estimating。
    use_cache=False 时忽略已有建筑缓存强制重新抓取。
    """
    def report(phase: str, detail: str = "") -> None:
        if progress:
            progress(phase, detail)

    report("reading", "读取建筑快照")
    lng_wgs, lat_wgs = gcj02_to_wgs84(target.longitude, target.latitude)
    paths = default_snapshot_paths() if snapshot_paths is None else snapshot_paths
    elements, covered = load_snapshot(
        lng_wgs, lat_wgs,
        snapshot_all=paths.get("all"),
        snapshot_buildings=paths.get("buildings"),
        snapshot_residential=paths.get("residential"),
    )
    if covered:
        report("estimating", "按本地快照聚类")
    else:
        report("fetching", "联网获取建筑数据")
        cache_path = cache_path_for(cache_dir or CACHE_DIR, target.community_id, lng_wgs, lat_wgs)
        elements = fetch_elements(lng_wgs, lat_wgs, cache_path,
                                  fetcher=fetcher, clock=clock, sleeper=sleeper, use_cache=use_cache)

    report("estimating", "聚类建筑面")
    members, low_confidence = select_members(elements, (lng_wgs, lat_wgs), target.community_name)
    if not members:
        raise EstimateError("no_geometry", "该定位附近没有可用的建筑面")
    ring, dropped_parts, _count = build_boundary_detail(members)

    warnings: list[str] = []
    if low_confidence:
        warnings.append("定位点未落在任何建筑簇内,轮廓取自最近的建筑簇,需人工确认范围")
    if dropped_parts:
        warnings.append(f"附近存在 {dropped_parts} 个未纳入的其他建筑簇,轮廓只覆盖最大的一簇")
    if len(members) == 1:
        warnings.append("仅有一个参考面,轮廓为单面近似")

    building_faces = sum(1 for m in members if m.kind == "building")
    residential_faces = sum(1 for m in members if m.kind == "residential")
    return EstimateOutcome(
        ring=ring,
        members=tuple(members),
        building_faces=building_faces,
        residential_faces=residential_faces,
        dropped_parts=dropped_parts,
        low_confidence=low_confidence,
        warnings=tuple(warnings),
        area_ha=round(area_ha(ring), 2),
    )
