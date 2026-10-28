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
import re
import threading
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from shapely.geometry import Point, Polygon
from shapely.ops import unary_union

from src.core.coordinates import gcj02_to_wgs84, wgs84_to_gcj02
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
ALGORITHM_VERSION = "v1"  # 估算策略版本,与查询版本分开;旧指纹不含本字段即过期
LANDUSE_GATE_M = 150.0    # 门口定位:到已匹配住宅面边界的最近距离容差
MIN_IDENTITY_CHARS = 4    # 短于观邸国际这类专名的通用词不参与包含匹配
WARN_TRUSTED_LANDUSE = "采用名称匹配的住宅用地面外轮廓,不是测绘或产权边界"
WARN_AMBIGUOUS_LANDUSE = "多个名称匹配的住宅用地面无法区分,已回退为建筑聚类"
WARN_FAR_SAME_NAME = "同名住宅用地距离过远,未作为可靠命中"
WARN_SPATIAL_FALLBACK = "未匹配到可信住宅用地,轮廓仅按附近建筑聚类估算,需人工确认"
WARN_LOW_CONFIDENCE = "定位点未落在任何建筑簇内,轮廓取自最近的建筑簇,需人工确认范围"
WARN_SINGLE_FACE = "仅有一个参考面,轮廓为单面近似"
_NAME_PUNCT = re.compile(r"[\s·・･•．.。,，、/／\\\-—–_~～'\"“”‘’()（）\[\]【】「」]+")
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
    aliases: tuple[str, ...] = ()


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


def normalize_place_name(value) -> str:
    """只去掉空白和常见标点,不删通名、不做模糊匹配。"""
    if value is None:
        return ""
    return _NAME_PUNCT.sub("", str(value))


def identity_match(element_name, known_names) -> bool:
    """受约束的双向包含。较短一侧短于 4 个字时拒绝,空名不命中。"""
    left = normalize_place_name(element_name)
    if len(left) < MIN_IDENTITY_CHARS:
        return False
    for known in known_names or ():
        right = normalize_place_name(known)
        if len(right) < MIN_IDENTITY_CHARS:
            continue
        shorter, longer = (left, right) if len(left) <= len(right) else (right, left)
        if shorter in longer:
            return True
    return False


def aliases_from_source(value) -> tuple[str, ...]:
    """只采用来源里已有的别名,不猜测。"""
    if value is None:
        return ()
    if isinstance(value, str):
        text = value.strip()
        return (text,) if text else ()
    if isinstance(value, (list, tuple)):
        items = []
        for item in value:
            if item is None:
                continue
            text = str(item).strip()
            if text:
                items.append(text)
        return tuple(items)
    return ()


def canonical_aliases(primary: str, aliases) -> tuple[str, ...]:
    """指纹用的别名:归一化、去掉与主名重复的项、去重后排序。"""
    primary_key = normalize_place_name(primary)
    seen: set[str] = set()
    result = []
    for alias in aliases or ():
        key = normalize_place_name(alias)
        if not key or key == primary_key or key in seen:
            continue
        seen.add(key)
        result.append(key)
    return tuple(sorted(result))


def _element_name(member: Member) -> str:
    return (member.element.get("tags") or {}).get("name") or ""


def _known_names(name, aliases) -> tuple[str, ...]:
    values = []
    if name:
        values.append(name)
    values.extend(aliases or ())
    return tuple(values)


def _usable_residential_polygon(poly) -> bool:
    """带洞或复合面不当作可信住宅面。"""
    return getattr(poly, "geom_type", None) == "Polygon" and not list(poly.interiors)


def _meters_between(lng1, lat1, lng2, lat2) -> float:
    return math.hypot(
        (lat1 - lat2) * 110574.0,
        (lng1 - lng2) * 111320.0 * math.cos(math.radians((lat1 + lat2) / 2)),
    )


def _boundary_distance_m(point: Point, poly: Polygon) -> float:
    if poly.covers(point):
        return 0.0
    nearest = poly.boundary.interpolate(poly.boundary.project(point))
    return _meters_between(point.x, point.y, nearest.x, nearest.y)


def _is_foreign_face(member: Member, known) -> bool:
    name = _element_name(member)
    return bool(name) and not identity_match(name, known)


def _inside_face(building: Member, face: Member) -> bool:
    return face.polygon.covers(building.polygon.representative_point())


def choose_trusted_landuse(landuse, point: Point, known_names) -> tuple[Member | None, str]:
    """身份命中且空间唯一时返回该面。status: hit / ambiguous / far / none。"""
    usable = [m for m in landuse if _usable_residential_polygon(m.polygon)]
    matched = [m for m in usable if identity_match(_element_name(m), known_names)]
    if not matched:
        return None, "none"
    containing = [m for m in matched if m.polygon.covers(point)]
    if len(containing) == 1:
        return containing[0], "hit"
    if len(containing) > 1:
        return None, "ambiguous"
    ranked = []
    for member in matched:
        distance = _boundary_distance_m(point, member.polygon)
        if distance <= LANDUSE_GATE_M:
            ranked.append((distance, member.element.get("id") or 0, member))
    if not ranked:
        return None, "far"
    ranked.sort(key=lambda item: (item[0], str(item[1])))
    if len(ranked) == 1 or ranked[1][0] - ranked[0][0] >= 1.0:
        return ranked[0][2], "hit"
    return None, "ambiguous"


def _cluster_buildings(rest: list[Member], point: Point, named_present: bool) -> tuple[list[Member], bool]:
    low_confidence = False
    if not rest:
        return [], low_confidence
    buf_deg = CLUSTER_GAP_M / 111574.0  # 近似 1m ≈ 1/111574°(滨江纬度下 ±5% 内)
    buffered = [m.polygon.buffer(buf_deg) for m in rest]
    merged = unary_union(buffered)
    parts = list(merged.geoms) if merged.geom_type == "MultiPolygon" else [merged]
    target = next((part for part in parts if part.covers(point) or part.distance(point) < 1e-6), None)
    if target is None:
        low_confidence = not named_present
        target = min(parts, key=lambda part: part.distance(point))
    cluster = [m for m, buf in zip(rest, buffered) if buf.intersects(target)]
    return cluster, low_confidence


def _building_selection(buildings, landuse, point: Point, known, status: str) -> tuple[list[Member], bool]:
    """建筑回退。定位若落在异名面内,只留该面里的楼,避免邻区簇把结果带走。"""
    named = [m for m in buildings if identity_match(_element_name(m), known)]
    named_ids = {id(m) for m in named}
    rest = [m for m in buildings if id(m) not in named_ids
            and _point_distance_m(point, m.polygon) <= MAX_CENTROID_M]
    containing_foreign = [face for face in landuse if _is_foreign_face(face, known) and face.polygon.covers(point)]
    if containing_foreign:
        inside = [m for m in rest if any(_inside_face(m, face) for face in containing_foreign)]
        if inside:
            rest = inside
        else:
            other_named = [face for face in landuse if _element_name(face) and face not in containing_foreign]
            rest = [m for m in rest if not any(_inside_face(m, face) for face in other_named)]
    if status == "far":
        far_faces = [
            face for face in landuse
            if _usable_residential_polygon(face.polygon) and identity_match(_element_name(face), known)
        ]
        rest = [m for m in rest if not any(_inside_face(m, face) for face in far_faces)]
    if not named and not rest:
        return [], True
    cluster, low_confidence = _cluster_buildings(rest, point, bool(named))
    return named + cluster, low_confidence


def select_members(elements, center_wgs, name, aliases=()) -> tuple[list[Member], bool]:
    """名称优先 + 距离过滤 + 连通聚簇。中心点须为 WGS84。

    不再用任意异名/未命名住宅面筛楼。返回 (成员面列表, low_confidence)。"""
    members = parse_members(elements)
    buildings = [m for m in members if m.kind == "building"]
    landuse = [m for m in members if m.kind == "residential"]
    point = Point(center_wgs)
    known = _known_names(name, aliases)
    return _building_selection(buildings, landuse, point, known, "none")


def _gcj_outer_ring(poly: Polygon) -> list[list[float]]:
    """直接采用外环,只去掉重复点和非数值,再转到 GCJ02。"""
    coords = []
    for lng, lat in poly.exterior.coords:
        if not (math.isfinite(lng) and math.isfinite(lat)):
            continue
        point = (lng, lat)
        if coords and coords[-1] == point:
            continue
        coords.append(point)
    if len(coords) >= 2 and coords[0] == coords[-1]:
        coords.pop()
    if len(coords) < 3:
        raise EstimateError("invalid_geometry", "合并后的轮廓顶点不足")
    ring = []
    for lng, lat in coords:
        glng, glat = wgs84_to_gcj02(lng, lat)
        ring.append([round(glng, 6), round(glat, 6)])
    if ring[0] != ring[-1]:
        ring.append(ring[0])
    return ring


def _empty_geometry_message(status: str, landuse, point: Point, known) -> str:
    if status == "ambiguous":
        return "多个名称匹配的住宅用地面无法区分,且没有可靠的建筑面"
    if status == "far":
        return "同名住宅用地距离过远,附近没有可靠的建筑面"
    if any(_is_foreign_face(face, known) and face.polygon.covers(point) for face in landuse):
        return "定位落在异名住宅用地内,不能采用邻区建筑轮廓"
    return "该定位附近没有可用的建筑面"


def _outcome(ring, members, *, warnings, low_confidence, dropped_parts) -> EstimateOutcome:
    return EstimateOutcome(
        ring=ring,
        members=tuple(members),
        building_faces=sum(1 for m in members if m.kind == "building"),
        residential_faces=sum(1 for m in members if m.kind == "residential"),
        dropped_parts=dropped_parts,
        low_confidence=low_confidence,
        warnings=tuple(warnings),
        area_ha=round(area_ha(ring), 2),
    )


def estimate_from_elements(elements, *, name, aliases=(), center_wgs) -> EstimateOutcome:
    """已有 OSM 要素上的估算。可信住宅面直接用外环,否则建筑聚类。"""
    members = parse_members(elements)
    buildings = [m for m in members if m.kind == "building"]
    landuse = [m for m in members if m.kind == "residential"]
    point = Point(center_wgs)
    known = _known_names(name, aliases)
    chosen, status = choose_trusted_landuse(landuse, point, known)
    if status == "hit" and chosen is not None:
        related = [b for b in buildings if _inside_face(b, chosen)]
        return _outcome(
            _gcj_outer_ring(chosen.polygon),
            [chosen, *related],
            warnings=[WARN_TRUSTED_LANDUSE],
            low_confidence=False,
            dropped_parts=0,
        )

    warnings: list[str] = []
    if status == "ambiguous":
        warnings.append(WARN_AMBIGUOUS_LANDUSE)
    elif status == "far":
        warnings.append(WARN_FAR_SAME_NAME)
    selected, low_confidence = _building_selection(buildings, landuse, point, known, status)
    if not selected:
        raise EstimateError("no_geometry", _empty_geometry_message(status, landuse, point, known))
    ring, dropped_parts, _count = build_boundary_detail(selected)
    if status == "none":
        warnings.append(WARN_SPATIAL_FALLBACK)
    if low_confidence:
        warnings.append(WARN_LOW_CONFIDENCE)
    if dropped_parts:
        warnings.append(f"附近存在 {dropped_parts} 个未纳入的其他建筑簇,轮廓只覆盖最大的一簇")
    if len(selected) == 1:
        warnings.append(WARN_SINGLE_FACE)
    return _outcome(
        ring, selected, warnings=warnings, low_confidence=low_confidence, dropped_parts=dropped_parts,
    )


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
                   *, clock=time.time, sleeper=time.sleep, timeout=REQUEST_TIMEOUT, use_cache=True,
                   budget_seconds=TASK_BUDGET_SECONDS):
    """带 7 天缓存与镜像 fallback 的 Overpass 抓取;返回 elements 列表。

    缓存内容记录查询 bbox 与版本,只有完全匹配才复用。use_cache=False 时忽略已有缓存
    强制重新抓取(用户显式选择"重新获取建筑")。

    整个任务受 budget_seconds 总预算约束:预算耗尽即放弃,不再逐个镜像试下去。
    """
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
    started = clock()
    for mirror in MIRRORS:
        remaining = budget_seconds - (clock() - started)
        if remaining <= 0:
            raise EstimateError("timeout", f"建筑数据获取超过 {budget_seconds:.0f} 秒预算")
        try:
            _pace(interval, clock, sleeper, injected=fetcher is not None)
            if fetcher:
                elements = fetcher(mirror, body)
            else:
                elements = _http_post(mirror, body, timeout=min(timeout, remaining))
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(
                {"version": QUERY_VERSION, "bbox": [round(v, 6) for v in bbox], "elements": elements},
                ensure_ascii=False), encoding="utf-8")
            return elements
        except EstimateError:
            raise
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


def _http_post(url, body, timeout=REQUEST_TIMEOUT):
    req = urllib.request.Request(url, data=body, headers={
        "User-Agent": USER_AGENT,
        "Content-Type": "application/x-www-form-urlencoded",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
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
    if use_cache:
        elements, covered = load_snapshot(
            lng_wgs, lat_wgs,
            snapshot_all=paths.get("all"),
            snapshot_buildings=paths.get("buildings"),
            snapshot_residential=paths.get("residential"),
        )
    else:
        # 用户显式选择"重新获取建筑": 连本地快照也不用, 直接联网取最新的
        elements, covered = [], False
    if covered:
        report("estimating", "按本地快照聚类")
    else:
        report("fetching", "联网获取建筑数据")
        cache_path = cache_path_for(cache_dir or CACHE_DIR, target.community_id, lng_wgs, lat_wgs)
        elements = fetch_elements(lng_wgs, lat_wgs, cache_path,
                                  fetcher=fetcher, clock=clock, sleeper=sleeper, use_cache=use_cache)

    report("estimating", "聚类建筑面")
    return estimate_from_elements(
        elements,
        name=target.community_name,
        aliases=target.aliases,
        center_wgs=(lng_wgs, lat_wgs),
    )
