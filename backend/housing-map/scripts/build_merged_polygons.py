"""按小区匹配 OSM 住宅轮廓并输出统一轮廓文件。

没有可靠 OSM 匹配的小区不输出边界，由地图仅显示其点位。
"""

import json
import math
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from src.services.community_filters import is_residential_community

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
OSM_PATH = os.path.join(DATA_DIR, 'binjiang_osm_residential.geojson')
COMM_PATH = os.path.join(DATA_DIR, 'binjiang_communities.json')
COORD_PATH = os.path.join(DATA_DIR, 'binjiang_coordinates.json')
PROPERTY_TYPES_PATH = os.path.join(DATA_DIR, 'property_types.json')
OUT_PATH = os.path.join(DATA_DIR, 'binjiang_polygons_merged.json')

NAME_MATCH_MAX_M = 800
M_PER_DEG = 111320




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


def select_residential_points(communities, coords, property_types):
    """返回与地图展示口径一致、且具备坐标的住宅小区。"""
    points = []
    filtered = 0
    for community in communities:
        community_id = community.get('community_id')
        coordinate = coords.get(community_id, {})
        if not coordinate.get('latitude'):
            continue
        if not is_residential_community(community, property_types):
            filtered += 1
            continue
        points.append((
            community_id,
            community.get('community_name', ''),
            coordinate['longitude'],
            coordinate['latitude'],
        ))
    return points, filtered


def main():
    osm = json.load(open(OSM_PATH, encoding='utf-8'))
    osm_feats = osm['features']
    osm_by_name = {normalize_name(f['properties']['name']): f for f in osm_feats if f['properties']['name']}
    print(f'OSM 轮廓: {len(osm_feats)}')

    communities = json.load(open(COMM_PATH, encoding='utf-8'))
    if isinstance(communities, dict):
        communities = communities['communities']
    coords = json.load(open(COORD_PATH, encoding='utf-8'))
    property_types = json.load(open(PROPERTY_TYPES_PATH, encoding='utf-8'))
    points, filtered = select_residential_points(communities, coords, property_types)
    print(f'已过滤非住宅/无效条目: {filtered}')
    print(f'住宅小区待匹配: {len(points)}')

    polygons = {}
    matched = 0
    unmatched = []
    for cid, name, lon, lat in points:
        osm_hit = match_osm(lon, lat, name, osm_feats, osm_by_name)
        if osm_hit:
            polygons[cid] = {'source': 'osm', 'rings': osm_hit[0]}
            matched += 1
        else:
            unmatched.append((cid, name, lon, lat))

    output = {
        '_meta': {
            'description': '小区边界轮廓合并数据 (GCJ-02)',
            'sources': ['OpenStreetMap landuse=residential'],
            'matched': {'osm': matched},
            'communities_with_coords': len(points),
        },
        'polygons': polygons,
    }
    temp_path = f'{OUT_PATH}.tmp'
    with open(temp_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False)
    os.replace(temp_path, OUT_PATH)
    for cid, name, lon, lat in unmatched:
        print(f'[未匹配] {cid} {name} ({lon:.6f}, {lat:.6f})')
    rate = matched / len(points) * 100 if points else 0
    print(f'OSM 匹配（住宅）: {matched}/{len(points)} = {rate:.0f}%')
    print(f'已保存 {OUT_PATH}')
    return {'matched': matched, 'unmatched': len(unmatched), 'total': len(points), 'filtered': filtered}


if __name__ == '__main__':
    main()
