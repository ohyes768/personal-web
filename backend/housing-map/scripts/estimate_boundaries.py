"""小区轮廓估算:Overpass 建筑聚类 → 外轮廓 → 候选输出 + 预览 HTML → 上传接口落盘。

一次性数据补齐工具(任务 10-16-boundary-estimate-script):
  python scripts/estimate_boundaries.py                       # 估算全部无轮廓小区
  python scripts/estimate_boundaries.py --ids 20000608        # 指定小区
  python scripts/estimate_boundaries.py --apply --selection estimate_out/selected.json
                                                              # 勾选结果经上传接口落盘
"""
import argparse
import json
import math
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from shapely.geometry import Point, Polygon
from shapely.ops import unary_union

from src.services.data_loader import DATA_DIR, load_display_communities

POLYGONS_PATH = DATA_DIR / "binjiang_polygons_merged.json"
SNAPSHOT_ALL = DATA_DIR / "binjiang_osm_buildings_all_raw.json"
SNAPSHOT_BUILDINGS = DATA_DIR / "binjiang_osm_named_buildings_raw.json"
SNAPSHOT_RESIDENTIAL = DATA_DIR / "binjiang_osm_residential_raw.json"
BINJIANG_BBOX = (30.10, 120.10, 30.26, 120.28)  # 滨江全域
OUT_DIR = PROJECT_ROOT / "estimate_out"
CACHE_DIR = OUT_DIR / "cache"
CACHE_TTL_DAYS = 7
REQUEST_INTERVAL = 10.0
MIRRORS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]
USER_AGENT = "housing-map-boundary-estimate/1.0 (personal project)"
BBOX_DEG = 0.002          # 定位点 ±0.002° ≈ ±220m
MAX_CENTROID_M = 250.0    # 楼质心距定位点上限
CLUSTER_GAP_M = 15.0      # 楼面 buffer 半径,使 ≤30m 间隙粘连成簇
FILL_M = 20.0             # 合并后填缝半径
SIMPLIFY_DEG = 0.0001

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
    dlng += (20.0 * math.sin(lng * _PI) + 40.0 * math.sin(lng / 3.0 * _PI)) * 2.0 / 3.0
    dlng += (150.0 * math.sin(lng / 12.0 * _PI) + 300.0 * math.sin(lng / 30.0 * _PI)) * 2.0 / 3.0
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
# 名单派生与 Overpass 客户端
# ---------------------------------------------------------------------------

def _read_json(path, fallback):
    if not Path(path).exists():
        return fallback
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def target_communities(ids=None, from_api=None):
    """目标 = 展示小区 ∩ 有坐标 ∩ 无轮廓。

    默认从本地 registry 派生;--from-api 时从线上地图接口派生(本地数据不全时用)。"""
    if from_api:
        req = urllib.request.Request(from_api, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.load(resp)["data"]
        targets = []
        for c in data:
            if not (c.get("latitude") and c.get("longitude")):
                continue
            if c.get("boundary"):
                continue
            targets.append({"community_id": str(c["community_id"]), "community_name": c["community_name"],
                            "longitude": c["longitude"], "latitude": c["latitude"]})
    else:
        targets = load_display_communities()
        polygons = _read_json(POLYGONS_PATH, {})
        known = {k for k in polygons if k != "_meta"}
        targets = [{**c, "community_id": str(c["community_id"])} for c in targets
                   if c.get("longitude") and c.get("latitude") and str(c["community_id"]) not in known]
    if ids:
        targets = [t for t in targets if t["community_id"] in ids]
    return targets


def overpass_query(lng, lat):
    s, w, n, e = lat - BBOX_DEG, lng - BBOX_DEG, lat + BBOX_DEG, lng + BBOX_DEG
    return (
        f"[out:json][timeout:60];"
        f'(way["building"]({s},{w},{n},{e});'
        f'way["landuse"="residential"]({s},{w},{n},{e}););'
        f"out geom;"
    )


def _as_elements(data):
    """Overpass dump 兼容:{"elements": [...]} 或裸 [...]。"""
    if isinstance(data, dict):
        return data.get("elements") or []
    return data if isinstance(data, list) else []


def load_snapshot(lng, lat):
    """本地快照取 bbox 内要素:优先全量楼快照(--refresh-snapshot 生成),否则旧具名快照。

    都缺失返回 None(交给在线)。"""
    if SNAPSHOT_ALL.exists():
        s, w, n, e = lat - BBOX_DEG, lng - BBOX_DEG, lat + BBOX_DEG, lng + BBOX_DEG
        picked = []
        for el in _as_elements(_read_json(SNAPSHOT_ALL, {})):
            geometry = [g for g in (el.get("geometry") or []) if g]
            if not geometry:
                continue
            mid_lng = sum(g["lon"] for g in geometry) / len(geometry)
            mid_lat = sum(g["lat"] for g in geometry) / len(geometry)
            if w <= mid_lng <= e and s <= mid_lat <= n:
                picked.append({**el, "geometry": geometry})
        return picked
    if not (SNAPSHOT_BUILDINGS.exists() and SNAPSHOT_RESIDENTIAL.exists()):
        return None
    s, w, n, e = lat - BBOX_DEG, lng - BBOX_DEG, lat + BBOX_DEG, lng + BBOX_DEG
    picked = []
    for path in (SNAPSHOT_BUILDINGS, SNAPSHOT_RESIDENTIAL):
        for el in _as_elements(_read_json(path, {})):
            geometry = [g for g in (el.get("geometry") or []) if g]
            if not geometry:
                continue
            mid_lng = sum(g["lon"] for g in geometry) / len(geometry)
            mid_lat = sum(g["lat"] for g in geometry) / len(geometry)
            if w <= mid_lng <= e and s <= mid_lat <= n:
                picked.append({**el, "geometry": geometry})
    return picked


def fetch_elements(lng_wgs, lat_wgs, cache_path, interval=REQUEST_INTERVAL, fetcher=None):
    """带 7 天缓存与镜像 fallback 的 Overpass 抓取;返回 elements 列表。"""
    if cache_path.exists():
        age_days = (time.time() - cache_path.stat().st_mtime) / 86400
        if age_days < CACHE_TTL_DAYS:
            return _read_json(cache_path, [])
    query = overpass_query(lng_wgs, lat_wgs)
    body = urllib.parse.urlencode({"data": query}).encode()
    errors = []
    do_fetch = fetcher or _http_post
    for mirror in MIRRORS:
        try:
            time.sleep(interval if not fetcher else 0)  # 真实请求间限速;测试注入 fetcher 不等待
            elements = do_fetch(mirror, body)
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(elements, ensure_ascii=False), encoding="utf-8")
            return elements
        except Exception as exc:  # noqa: BLE001 - 镜像逐个降级,任何失败都换下一个
            errors.append(f"{mirror}: {exc}")
    raise RuntimeError("所有 Overpass 镜像均失败:\n" + "\n".join(errors))


def _http_post(url, body):
    req = urllib.request.Request(url, data=body, headers={
        "User-Agent": USER_AGENT,
        "Content-Type": "application/x-www-form-urlencoded",
    })
    with urllib.request.urlopen(req, timeout=90) as resp:
        return json.load(resp)["elements"]


# ---------------------------------------------------------------------------
# 挑楼聚类与轮廓生成
# ---------------------------------------------------------------------------

def refresh_snapshot(interval=REQUEST_INTERVAL, fetcher=None):
    """全滨江抓取所有 building + residential 面,写入全量快照(具名与否不限)。"""
    s, w, n, e = BINJIANG_BBOX
    query = (
        f"[out:json][timeout:300];"
        f'(way["building"]({s},{w},{n},{e});'
        f'way["landuse"="residential"]({s},{w},{n},{e}););'
        f"out geom;"
    )
    body = urllib.parse.urlencode({"data": query}).encode()
    errors = []
    do_fetch = fetcher or _http_post
    for mirror in MIRRORS:
        try:
            if not fetcher:
                time.sleep(interval)
            elements = do_fetch(mirror, body)
            SNAPSHOT_ALL.write_text(json.dumps({"elements": elements}, ensure_ascii=False), encoding="utf-8")
            print(f"全量快照已写入 {SNAPSHOT_ALL.name}({len(elements)} 要素,来源 {mirror})")
            return len(elements)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{mirror}: {exc}")
    raise RuntimeError("所有 Overpass 镜像均失败:\n" + "\n".join(errors) +
                       "\n提示:本机出口可能无法直连 Overpass,可设置 HTTPS_PROXY 后重试")


def _parse_elements(elements):
    """elements -> (buildings[(element, polygon)], landuse[(element, polygon)]),非法几何丢弃。"""
    buildings, landuse = [], []
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
        if (el.get("tags") or {}).get("landuse") == "residential":
            landuse.append((el, poly))
        else:
            buildings.append((el, poly))
    return buildings, landuse


def _point_distance_m(point, poly):
    dlat = point.y - poly.centroid.y
    dlng = point.x - poly.centroid.x
    return math.hypot(dlat * 110574.0, dlng * 111320.0 * math.cos(math.radians(point.y)))


def _name_hit(el_name, community_name):
    """双向包含:楼名"倾城之恋3幢"与小区名"顺发倾城之恋"互为子串即命中。"""
    if not community_name or not el_name:
        return False
    return community_name in el_name or el_name in community_name


def select_buildings(elements, center_wgs, name):
    """名称优先 + 距离过滤 + landuse 收编 + 连通聚簇;中心点须为 WGS84(与 OSM 同系)。

    名称命中的楼与具名 residential 面(小区边界本体)无条件入选;其余楼聚类后取含定位点的簇。
    返回 (成员面列表, low_confidence)。"""
    buildings, landuse_pairs = _parse_elements(elements)
    point = Point(center_wgs)

    named = [poly for el, poly in buildings if _name_hit((el.get("tags") or {}).get("name"), name)]
    named_residential = [poly for el, poly in landuse_pairs if _name_hit((el.get("tags") or {}).get("name"), name)]
    rest = [poly for el, poly in buildings if not _name_hit((el.get("tags") or {}).get("name"), name)]
    rest = [poly for poly in rest if _point_distance_m(point, poly) <= MAX_CENTROID_M]
    other_landuse = [poly for el, poly in landuse_pairs if poly not in named_residential]
    if other_landuse:
        inside = [poly for poly in rest if any(poly.within(lu) for lu in other_landuse)]
        if inside:
            rest = inside
    if not named and not named_residential and not rest:
        return [], True

    low_confidence = False
    cluster: list = []
    if rest:
        buf_deg = CLUSTER_GAP_M / 111574.0  # 近似 1m ≈ 1/111574°(滨江纬度下 ±5% 内)
        buffered = [poly.buffer(buf_deg) for poly in rest]
        merged = unary_union(buffered)
        parts = list(merged.geoms) if merged.geom_type == "MultiPolygon" else [merged]
        target = next((part for part in parts if part.covers(point) or part.distance(point) < 1e-6), None)
        if target is None:
            # 名称已给出可信成员时不降置信;仅裸聚类取最近簇时才标低置信
            low_confidence = not (named or named_residential)
            target = min(parts, key=lambda part: part.distance(point))
        cluster = [poly for poly, buf in zip(rest, buffered) if buf.intersects(target)]
    return named + named_residential + cluster, low_confidence


def build_boundary(members):
    """成员面合并 → 填缝 → 最大外环 → 简化;外环逐点转 GCJ02 输出。"""
    merged = unary_union(members)
    fill_deg = FILL_M / 111574.0
    filled = merged.buffer(fill_deg).buffer(-fill_deg)
    polys = list(filled.geoms) if filled.geom_type == "MultiPolygon" else [filled]
    biggest = max(polys, key=lambda poly: poly.area)
    ring = biggest.simplify(SIMPLIFY_DEG).exterior.coords[:]
    gcj_ring = []
    for lng, lat in ring:
        glng, glat = wgs84_to_gcj02(lng, lat)
        gcj_ring.append([round(glng, 6), round(glat, 6)])
    return gcj_ring, len(members)


# ---------------------------------------------------------------------------
# 输出:候选 geojson + 预览 HTML
# ---------------------------------------------------------------------------

def estimate_all(ids=None, interval=REQUEST_INTERVAL, fetcher=None, online=False, from_api=None):
    targets = target_communities(ids, from_api=from_api)
    polygons = _read_json(POLYGONS_PATH, {})
    results, failures = [], []
    snapshot_ready = SNAPSHOT_BUILDINGS.exists() and SNAPSHOT_RESIDENTIAL.exists()
    if online:
        print("模式:在线 Overpass(--online)")
    elif snapshot_ready:
        print("模式:本地 OSM 快照(默认;--online 改为在线抓取)")
    for index, community in enumerate(targets):
        cid, name = community["community_id"], community["community_name"]
        print(f"[{index + 1}/{len(targets)}] {name} ({cid}) ...", flush=True)
        lng_wgs, lat_wgs = gcj02_to_wgs84(community["longitude"], community["latitude"])
        cache_path = CACHE_DIR / f"{cid}.json"
        try:
            if not online and snapshot_ready:
                elements = load_snapshot(lng_wgs, lat_wgs)
            else:
                elements = fetch_elements(lng_wgs, lat_wgs, cache_path, interval=interval, fetcher=fetcher)
            members, low_confidence = select_buildings(elements, (lng_wgs, lat_wgs), name)
            if not members:
                failures.append({"community_id": cid, "name": name, "error": "无建筑可聚类"})
                continue
            ring_gcj, building_count = build_boundary(members)
            results.append({
                "community_id": cid,
                "name": name,
                "center": [community["longitude"], community["latitude"]],
                "rings": [ring_gcj],
                "meta": {
                    "building_count": building_count,
                    "low_confidence": low_confidence,
                    "estimated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                },
            })
        except Exception as exc:  # noqa: BLE001 - 单小区失败不阻断批次
            failures.append({"community_id": cid, "name": name, "error": str(exc)})
    return results, failures


def _area_ha(ring):
    lat0 = sum(p[1] for p in ring) / len(ring)
    km_lat, km_lng = 110.574, 111.320 * math.cos(math.radians(lat0))
    pts = [(p[0] * km_lng, p[1] * km_lat) for p in ring]
    doubled = sum((x1 * y2 - x2 * y1) for (x1, y1), (x2, y2) in zip(pts, pts[1:]))
    return abs(doubled) / 2 * 100


def _amap_credentials():
    """从 housing-map 前端 env 读 (key, security_js_code)。"""
    values = {}
    for name in (".env.local", ".env"):
        path = PROJECT_ROOT.parents[1] / "apps" / "housing-map" / name
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            stripped = line.strip()
            for env_key in ("NEXT_PUBLIC_GAODE_MAP_KEY", "NEXT_PUBLIC_GAODE_SECURITY_KEY",
                            "NEXT_PUBLIC_GAODE_MAP_SECURITY_KEY"):
                if stripped.startswith(env_key + "=") and env_key not in values:
                    values[env_key] = stripped.split("=", 1)[1].strip().strip('"').strip("'")
    return values.get("NEXT_PUBLIC_GAODE_MAP_KEY"), values.get("NEXT_PUBLIC_GAODE_SECURITY_KEY")


PREVIEW_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>小区轮廓估算预览</title>
<style>
body{margin:0;font-family:system-ui,sans-serif;display:flex;height:100vh}
#map{flex:1}#side{width:320px;overflow-y:auto;padding:12px;background:#fafaf7;font-size:13px}
.item{border-bottom:1px solid #e5e2da;padding:8px 4px;cursor:pointer}
.item.low{background:#fff4e5}
.small{color:#888;font-size:12px}
button{margin:12px 0;padding:8px 16px;width:100%}
.hint{background:#fff8dc;border:1px solid #e0d8a8;padding:6px;margin-bottom:8px}
</style></head><body>
<div id="map"></div><div id="side">
__KEY_HINT__
<button onclick="exportSelection()">导出勾选 selected.json</button>
<div id="list"></div></div>
<script>window.PREVIEW_DATA = __DATA__;</script>
<script>
window._AMapSecurityConfig = {securityJsCode: '__SECURITY__'};
</script>
<script src="https://webapi.amap.com/maps?v=2.0&key=__KEY__"></script>
<script>
const DATA = window.PREVIEW_DATA;
const map = new AMap.Map('map', {viewMode: '2D', zoom: 15, mapStyle: 'amap://styles/whitesmoke'});
const bounds = [];
DATA.existing.forEach(ring => {
  const poly = new AMap.Polygon({path: ring, strokeColor: '#999', strokeWeight: 1, fillOpacity: 0.03, bubble: true});
  map.add(poly);
});
DATA.candidates.forEach((c, i) => {
  const color = ['#d04a3a','#3a7bd0','#2f9e57','#c78a1f','#7a4ad0'][i % 5];
  const poly = new AMap.Polygon({path: c.rings[0], strokeColor: color, fillColor: color,
    fillOpacity: 0.35, strokeWeight: 2, bubble: true});
  map.add(poly); bounds.push(poly);
  new AMap.CircleMarker({center: c.center, radius: 5, fillColor: '#111', fillOpacity: 1,
    strokeColor: '#fff', strokeWeight: 1}).setMap(map);
});
map.setFitView(bounds);
const list = document.getElementById('list');
DATA.candidates.forEach((c, i) => {
  const div = document.createElement('div');
  div.className = 'item' + (c.meta.low_confidence ? ' low' : '');
  const ha = Math.round(c.area_ha * 10) / 10;
  div.innerHTML = `<label><input type="checkbox" checked data-cid="${c.community_id}">
    <b>${c.name}</b></label>
    <div class="small">${c.community_id} · ${c.meta.building_count} 栋 · ${ha} 公顷
    ${c.meta.low_confidence ? ' · <span style="color:#c60">低置信</span>' : ''}</div>`;
  div.querySelector('input').addEventListener('change', e => {
    c._selected = e.target.checked;
    e.target.closest('.item').style.opacity = e.target.checked ? 1 : 0.4;
  });
  div.addEventListener('click', ev => {
    if (ev.target.tagName !== 'INPUT') map.setFitView(bounds.filter((_, j) => DATA.candidates[j].community_id === c.community_id));
  });
  list.appendChild(div);
});
function exportSelection() {
  const picked = DATA.candidates.filter(c => c._selected !== false);
  if (!picked.length) { alert('未勾选任何小区'); return; }
  const blob = new Blob([JSON.stringify(picked.map(c => ({community_id: c.community_id, name: c.name, rings: c.rings, meta: c.meta})), null, 1)],
    {type: 'application/json'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob); a.download = 'selected.json'; a.click();
}
</script></body></html>
"""


def write_outputs(results, failures):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for result in results:
        result["area_ha"] = round(_area_ha(result["rings"][0]), 2)
    candidates_geojson = {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "properties": {"community_id": r["community_id"], "name": r["name"], **r["meta"], "area_ha": r["area_ha"]},
            "geometry": {"type": "Polygon", "coordinates": r["rings"]},
        } for r in results],
    }
    (OUT_DIR / "candidates.geojson").write_text(
        json.dumps(candidates_geojson, ensure_ascii=False, indent=1), encoding="utf-8")
    (OUT_DIR / "failures.json").write_text(
        json.dumps(failures, ensure_ascii=False, indent=1), encoding="utf-8")

    existing = []
    for cid, entry in _read_json(POLYGONS_PATH, {}).items():
        if cid == "_meta" or entry.get("source") != "osm":
            continue
        for ring in entry.get("rings", []):
            existing.append(ring)
    key, security = _amap_credentials()
    key_hint = "" if key else '<div class="hint">未读到 NEXT_PUBLIC_GAODE_MAP_KEY,地图空白时请填入下方 __KEY__ 处</div>'
    html = (PREVIEW_TEMPLATE
            .replace("__DATA__", json.dumps({"candidates": results, "existing": existing}, ensure_ascii=False))
            .replace("__KEY__", key or "YOUR_AMAP_KEY")
            .replace("__SECURITY__", security or "")
            .replace("__KEY_HINT__", key_hint))
    (OUT_DIR / "estimate_preview.html").write_text(html, encoding="utf-8")
    print(f"候选 {len(results)} 个 / 失败 {len(failures)} 个 -> {OUT_DIR}")
    print("预览请走 HTTP(高德 SDK 拒绝 file://):")
    print(f'  cd "{OUT_DIR}" && python -m http.server 8917')
    print("  浏览器打开 http://localhost:8917/estimate_preview.html")


# ---------------------------------------------------------------------------
# --apply:经上传接口落盘
# ---------------------------------------------------------------------------

def apply_selection(selection_path, api_base, token):
    selected = json.loads(Path(selection_path).read_text(encoding="utf-8-sig"))
    if not token:
        raise SystemExit("缺少 token:设 HOUSING_ADMIN_TOKEN 环境变量或传 --token")
    accepted, failed = [], []
    for item in selected:
        body = json.dumps({
            "source": "osm-building",
            "boundaries": [{
                "community_id": item["community_id"],
                "coordinate_system": "gcj02",
                "rings": item["rings"],
                "meta": item.get("meta"),
            }],
        }).encode()
        req = urllib.request.Request(
            f"{api_base.rstrip('/')}/api/boundaries/import", data=body,
            headers={"Content-Type": "application/json", "X-Admin-Token": token})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.load(resp)["data"]
            if data["accepted"]:
                accepted.append(item["community_id"])
                print(f"√ {item.get('name', item['community_id'])} 已落盘")
            else:
                reason = data["rejected"][0]["reason"] if data["rejected"] else "unknown"
                failed.append((item["community_id"], reason))
                print(f"× {item.get('name', item['community_id'])}: {reason}")
        except Exception as exc:  # noqa: BLE001 - 上传失败列出清单,接口幂等可重跑
            failed.append((item["community_id"], str(exc)))
            print(f"× {item['community_id']}: {exc}")
    print(f"完成 {len(accepted)} / 失败 {len(failed)};接口幂等,可修正后重跑")


def main(argv=None):
    parser = argparse.ArgumentParser(description="OSM 建筑聚类估算小区轮廓")
    parser.add_argument("--ids", nargs="*", help="仅处理指定 community_id")
    parser.add_argument("--apply", action="store_true", help="上传 selected.json 到后端接口")
    parser.add_argument("--selection", default=str(OUT_DIR / "selected.json"))
    parser.add_argument("--api", default="http://localhost:8096")
    parser.add_argument("--token", default=None)
    parser.add_argument("--interval", type=float, default=REQUEST_INTERVAL, help="Overpass 请求间隔秒")
    parser.add_argument("--online", action="store_true", help="跳过本地快照,强制在线抓取")
    parser.add_argument("--refresh-snapshot", action="store_true", help="全滨江重抓全量楼快照后退出")
    parser.add_argument("--from-api", default=None, help="从线上地图接口派生目标(如 https://host/api/map/communities)")
    args = parser.parse_args(argv)

    if args.apply:
        apply_selection(args.selection, args.api, args.token or __import__("os").environ.get("HOUSING_ADMIN_TOKEN"))
        return
    if args.refresh_snapshot:
        refresh_snapshot(interval=args.interval)
        return
    ids = set(args.ids) if args.ids else None
    results, failures = estimate_all(ids, interval=args.interval, online=args.online, from_api=args.from_api)
    write_outputs(results, failures)
    if failures:
        print("失败清单:")
        for f in failures:
            print(f"  {f['name']} ({f['community_id']}): {f['error']}")


if __name__ == "__main__":
    main()
