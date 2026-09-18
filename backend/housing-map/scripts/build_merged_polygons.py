"""
合并 Shapefile 与 OSM 两份住宅轮廓，按小区匹配后输出统一轮廓文件。

匹配策略（每个小区，OSM 优先）:
1. OSM landuse=residential 点在面内匹配，其次名称匹配（去"小区/公寓/住宅区"后缀后比对）
2. Shapefile 最近邻匹配（≤150米），全局统一按 WGS84 -> GCJ-02 转换
   （坐标系已用 OSM 轮廓做参照校准: wgs84->gcj02 中位偏差 51m,
     原样/BD-09 解释偏差 216m+/230m+, 见 2026-09-15 诊断）

输入:
- data/_temp_extract/Hangzhou_202302.shp
- data/binjiang_osm_residential.geojson (GCJ-02, 由 convert_osm_residential.py 生成)
- data/binjiang_communities.json + data/binjiang_coordinates.json

输出:
- data/binjiang_polygons_merged.json (GCJ-02, community_id -> rings)
"""

import json
import math
import os
import struct

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
SHP_PATH = os.path.join(DATA_DIR, '_temp_extract', 'Hangzhou_202302.shp')
OSM_PATH = os.path.join(DATA_DIR, 'binjiang_osm_residential.geojson')
COMM_PATH = os.path.join(DATA_DIR, 'binjiang_communities.json')
COORD_PATH = os.path.join(DATA_DIR, 'binjiang_coordinates.json')
OUT_PATH = os.path.join(DATA_DIR, 'binjiang_polygons_merged.json')

MATCH_THRESHOLD_M = 200
NAME_MATCH_MAX_M = 800
M_PER_DEG = 111320


def transform_lat(x: float, y: float) -> float:
    ret = -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * math.sqrt(abs(x))
    ret += (20.0 * math.sin(6.0 * x * math.pi) + 20.0 * math.sin(2.0 * x * math.pi)) * 2.0 / 3.0
    ret += (20.0 * math.sin(y * math.pi) + 40.0 * math.sin(y / 3.0 * math.pi)) * 2.0 / 3.0
    ret += (160.0 * math.sin(y / 12.0 * math.pi) + 320 * math.sin(y * math.pi / 30.0)) * 2.0 / 3.0
    return ret


def transform_lon(x: float, y: float) -> float:
    ret = 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * math.sqrt(abs(x))
    ret += (20.0 * math.sin(6.0 * x * math.pi) + 20.0 * math.sin(2.0 * x * math.pi)) * 2.0 / 3.0
    ret += (20.0 * math.sin(x * math.pi) + 40.0 * math.sin(x / 3.0 * math.pi)) * 2.0 / 3.0
    ret += (150.0 * math.sin(x / 12.0 * math.pi) + 300.0 * math.sin(x / 30.0 * math.pi)) * 2.0 / 3.0
    return ret


def wgs84_to_gcj02(lon: float, lat: float) -> tuple[float, float]:
    a = 6378245.0
    ee = 0.00669342162296594323
    dlat = transform_lat(lon - 105.0, lat - 35.0)
    dlon = transform_lon(lon - 105.0, lat - 35.0)
    radlat = lat / 180.0 * math.pi
    magic = 1 - ee * math.sin(radlat) ** 2
    sqrtmagic = math.sqrt(magic)
    dlat = (dlat * 180.0) / ((a * (1 - ee)) / (magic * sqrtmagic) * math.pi)
    dlon = (dlon * 180.0) / (a / sqrtmagic * math.cos(radlat) * math.pi)
    return lon + dlon, lat + dlat


def read_shp_polygons(path: str) -> list[list[list[tuple]]]:
    """读取 SHP 中 type=5 (Polygon) 的全部环, 返回 [rings], 每个 ring 为 [(lon,lat),...]"""
    polygons = []
    with open(path, 'rb') as f:
        data = f.read()
    offset = 100
    while offset < len(data) - 12:
        content_len = struct.unpack('>I', data[offset + 4:offset + 8])[0]
        shape_type = struct.unpack('<I', data[offset + 8:offset + 12])[0]
        rec_end = offset + 8 + content_len * 2
        if shape_type == 5:
            b = offset + 12
            num_parts = struct.unpack('<i', data[b + 32:b + 36])[0]
            num_points = struct.unpack('<i', data[b + 36:b + 40])[0]
            parts_off = b + 40
            starts = [struct.unpack('<i', data[parts_off + i * 4:parts_off + i * 4 + 4])[0]
                      for i in range(num_parts)] + [num_points]
            pts_off = parts_off + num_parts * 4
            pts = [(struct.unpack('<d', data[pts_off + i * 16:pts_off + i * 16 + 8])[0],
                    struct.unpack('<d', data[pts_off + i * 16 + 8:pts_off + i * 16 + 16])[0])
                   for i in range(num_points)]
            polygons.append([pts[starts[i]:starts[i + 1]] for i in range(num_parts)])
        offset = rec_end
    return polygons


def seg_dist(px, py, x1, y1, x2, y2) -> float:
    dx, dy = x2 - x1, y2 - y1
    l2 = dx * dx + dy * dy
    if l2 == 0:
        return math.hypot(px - x1, py - y1)
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / l2))
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))


def point_to_rings_m(lon: float, lat: float, rings: list) -> float:
    """点到多边形各环的最近距离(米), 点在内部时为 0"""
    best = 1e9
    for ring in rings:
        xs = [p[0] for p in ring]
        ys = [p[1] for p in ring]
        if not (min(xs) - 0.001 <= lon <= max(xs) + 0.001 and min(ys) - 0.001 <= lat <= max(ys) + 0.001):
            continue
        for i in range(len(ring) - 1):
            d = seg_dist(lon, lat, ring[i][0], ring[i][1], ring[i + 1][0], ring[i + 1][1]) * M_PER_DEG
            if d < best:
                best = d
    return best


def point_in_ring(x: float, y: float, ring: list) -> bool:
    inside = False
    for i in range(len(ring) - 1):
        x1, y1 = ring[i]
        x2, y2 = ring[i + 1]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def normalize_name(name: str) -> str:
    for suffix in ('小区', '公寓', '住宅区'):
        if name.endswith(suffix) and len(name) > len(suffix):
            name = name[: -len(suffix)]
    return name


def match_shapefile(lon: float, lat: float, shp_gcj):
    """单一坐标解释(WGS84->GCJ-02)下最近邻匹配, 返回 (rings, 距离m) 或 None"""
    best = None
    for rings in shp_gcj:
        d = point_to_rings_m(lon, lat, rings)
        if d <= MATCH_THRESHOLD_M and (best is None or d < best[0]):
            best = (d, rings)
    return best


def match_osm(lon, lat, name, osm_feats, osm_by_name):
    # landuse(住宅用地,围墙级)优先于 building(带名建筑,楼栋级)
    landuse = [f for f in osm_feats if f['properties'].get('kind') != 'building']
    building = [f for f in osm_feats if f['properties'].get('kind') == 'building']

    for pool in (landuse, building):
        # 1) 点在面内
        for ft in pool:
            ring = ft['geometry']['coordinates'][0]
            xs = [p[0] for p in ring]
            ys = [p[1] for p in ring]
            if min(xs) <= lon <= max(xs) and min(ys) <= lat <= max(ys) and point_in_ring(lon, lat, ring):
                return ft['geometry']['coordinates'], ft['properties']['name']
        # 2) 150m 内最近轮廓(定位点常打在小区门口/路侧)
        best = None
        for ft in pool:
            d = point_to_rings_m(lon, lat, ft['geometry']['coordinates'])
            if d <= 150 and (best is None or d < best[0]):
                best = (d, ft)
        if best:
            return best[1]['geometry']['coordinates'], best[1]['properties']['name']

    # 3) 名称匹配需距离校验, 防止同名小区跨区错配
    ft = osm_by_name.get(normalize_name(name))
    if ft:
        rings = ft['geometry']['coordinates']
        if point_to_rings_m(lon, lat, rings) <= NAME_MATCH_MAX_M:
            return rings, ft['properties']['name']
    return None


def main():
    shp_raw = read_shp_polygons(SHP_PATH)
    # 全局统一 WGS84 -> GCJ-02
    shp_gcj = [[[wgs84_to_gcj02(x, y) for x, y in ring] for ring in rings] for rings in shp_raw]
    # 只保留滨江区宽范围内的多边形(按转换后坐标), 减少匹配扫描量
    shp_gcj = [rings for rings in shp_gcj
               if 120.08 <= min(p[0] for p in rings[0]) and max(p[0] for p in rings[0]) <= 120.30
               and 30.10 <= min(p[1] for p in rings[0]) and max(p[1] for p in rings[0]) <= 30.30]
    print(f'Shapefile 滨江区范围多边形(WGS84->GCJ-02): {len(shp_gcj)}')

    osm = json.load(open(OSM_PATH, encoding='utf-8'))
    osm_feats = osm['features']
    osm_by_name = {normalize_name(f['properties']['name']): f for f in osm_feats if f['properties']['name']}
    print(f'OSM 轮廓: {len(osm_feats)}')

    communities = json.load(open(COMM_PATH, encoding='utf-8'))
    if isinstance(communities, dict):
        communities = communities['communities']
    coords = json.load(open(COORD_PATH, encoding='utf-8'))
    points = [(c['community_id'], c.get('community_name', ''), coords[c['community_id']]['longitude'], coords[c['community_id']]['latitude'])
              for c in communities if coords.get(c.get('community_id'), {}).get('latitude')]

    polygons = {}
    stat = {'osm': 0, 'shp': 0}
    for cid, name, lon, lat in points:
        osm_hit = match_osm(lon, lat, name, osm_feats, osm_by_name)
        if osm_hit:
            polygons[cid] = {'source': 'osm', 'rings': osm_hit[0]}
            stat['osm'] += 1
            continue
        hit = match_shapefile(lon, lat, shp_gcj)
        if hit:
            polygons[cid] = {'source': 'shp', 'rings': [[list(p) for p in ring] for ring in hit[1]]}
            stat['shp'] += 1

    output = {
        '_meta': {
            'description': '小区边界轮廓合并数据 (GCJ-02)',
            'sources': ['Hangzhou_202302.shp', 'OpenStreetMap landuse=residential'],
            'match_threshold_m': MATCH_THRESHOLD_M,
            'matched': stat,
            'communities_with_coords': len(points),
        },
        'polygons': polygons,
    }
    with open(OUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False)
    total = stat['shp'] + stat['osm']
    print(f'Shapefile 匹配: {stat["shp"]}, OSM 补充: {stat["osm"]}')
    print(f'合计: {total}/{len(points)} = {total / len(points) * 100:.0f}%')
    print(f'已保存 {OUT_PATH}')


if __name__ == '__main__':
    main()
