"""
将滨江区 OSM 公交/地铁路线 + 站点 raw 数据转换为 GCJ-02 GeoJSON,
供前端 AMap.Polyline / AMap.Marker 渲染使用。

输入:
- data/binjiang_osm_transit_routes_raw.json  Overpass out geom
- data/binjiang_osm_transit_stops_raw.json   Overpass out center

输出:
- data/binjiang_transit_routes.geojson  GeoJSON LineString 集合 (GCJ-02)
  properties: ref / name / route (subway/bus) / operator / member_count
- data/binjiang_transit_stops.geojson   GeoJSON Point 集合 (GCJ-02)
  properties: name / route (subway/bus/railway) / network / operator
"""

from __future__ import annotations

import json
import math
import os

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
ROUTES_RAW = os.path.join(DATA_DIR, 'binjiang_osm_transit_routes_raw.json')
STOPS_RAW = os.path.join(DATA_DIR, 'binjiang_osm_transit_stops_raw.json')
ROUTES_OUT = os.path.join(DATA_DIR, 'binjiang_transit_routes.geojson')
STOPS_OUT = os.path.join(DATA_DIR, 'binjiang_transit_stops.geojson')


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
    if 72.004 <= lon <= 137.8347 and 0.8293 <= lat <= 55.8271:
        a = 6378245.0
        ee = 0.00669342162296594323
        dlat = transform_lat(lon - 105.0, lat - 35.0)
        dlon = transform_lon(lon - 105.0, lat - 35.0)
        radlat = lat / 180.0 * math.pi
        magic = math.sin(radlat)
        magic = 1 - ee * magic * magic
        sqrtmagic = math.sqrt(magic)
        dlat = (dlat * 180.0) / ((a * (1 - ee)) / (magic * sqrtmagic) * math.pi)
        dlon = (dlon * 180.0) / (a / sqrtmagic * math.cos(radlat) * math.pi)
        return lon + dlon, lat + dlat
    return lon, lat


def assemble_route_line(rel: dict) -> list[list[float]] | None:
    """把 relation 的 outer 成员按出现顺序拼成一个 LineString (GCJ-02)"""
    coords: list[list[float]] = []
    for member in rel.get('members', []):
        if member.get('type') != 'way' or member.get('role') not in ('outer', '', None):
            continue
        for pt in member.get('geometry') or []:
            lon, lat = wgs84_to_gcj02(pt['lon'], pt['lat'])
            coords.append([lon, lat])
    # 去掉相邻重复点 (各 way 连接处)
    cleaned: list[list[float]] = []
    for c in coords:
        if not cleaned or cleaned[-1] != c:
            cleaned.append(c)
    return cleaned if len(cleaned) >= 2 else None


def main():
    raw_routes = json.load(open(ROUTES_RAW, encoding='utf-8'))
    features: list[dict] = []
    route_counts = {'subway': 0, 'bus': 0, 'other': 0}
    skipped_short = 0
    for rel in raw_routes['elements']:
        if rel.get('type') != 'relation':
            continue
        tags = rel.get('tags', {})
        route = tags.get('route', '')
        line = assemble_route_line(rel)
        if line is None:
            skipped_short += 1
            continue
        bucket = route if route in route_counts else 'other'
        route_counts[bucket] += 1
        features.append({
            'type': 'Feature',
            'properties': {
                'osm_id': rel['id'],
                'route': route,
                'ref': tags.get('ref', ''),
                'name': tags.get('name', ''),
                'operator': tags.get('operator', ''),
                'network': tags.get('network', ''),
                'colour': tags.get('colour', ''),  # OSM 官方配色 (如 '1号线' 红/绿)
                'member_count': len(rel.get('members', [])),
            },
            'geometry': {'type': 'LineString', 'coordinates': line},
        })

    geojson = {
        'type': 'FeatureCollection',
        '_meta': {'source': 'OpenStreetMap Overpass', 'coord_system': 'GCJ-02'},
        'features': features,
    }
    with open(ROUTES_OUT, 'w', encoding='utf-8') as f:
        json.dump(geojson, f, ensure_ascii=False)
    print(f'路线: 写入 {len(features)} 条 ({route_counts["subway"]} 地铁 / {route_counts["bus"]} 公交 / {route_counts["other"]} 其他), 跳过 {skipped_short} 条过短')

    raw_stops = json.load(open(STOPS_RAW, encoding='utf-8'))
    stop_features: list[dict] = []
    for el in raw_stops['elements']:
        tags = el.get('tags', {})
        name = tags.get('name', '')
        if not name:
            continue
        # node: lat/lon 在顶层; way: out center 会在 center 下; way out geom 取几何中心
        center = None
        if 'lat' in el and 'lon' in el:
            center = {'lat': el['lat'], 'lon': el['lon']}
        elif el.get('center'):
            center = el['center']
        elif el.get('type') == 'way':
            geom = el.get('geometry') or []
            if geom:
                center = {'lat': sum(p['lat'] for p in geom)/len(geom), 'lon': sum(p['lon'] for p in geom)/len(geom)}
        if center is None or 'lat' not in center or 'lon' not in center:
            continue
        # 站点分类: railway=station/subway 为地铁站, railway=halt/stop 为火车站, highway=bus_stop 公交
        rail = tags.get('railway', '')
        if rail in ('station', 'subway'):
            kind = 'subway'
        elif rail in ('halt', 'stop'):
            kind = 'railway'
        elif tags.get('highway') == 'bus_stop':
            kind = 'bus'
        else:
            kind = 'other'
        lon, lat = wgs84_to_gcj02(center['lon'], center['lat'])
        stop_features.append({
            'type': 'Feature',
            'properties': {
                'osm_id': el['id'],
                'name': name,
                'kind': kind,
                'network': tags.get('network', ''),
                'operator': tags.get('operator', ''),
                'route_ref': tags.get('ref', ''),
            },
            'geometry': {'type': 'Point', 'coordinates': [lon, lat]},
        })
    geojson_stops = {
        'type': 'FeatureCollection',
        '_meta': {'source': 'OpenStreetMap Overpass', 'coord_system': 'GCJ-02'},
        'features': stop_features,
    }
    with open(STOPS_OUT, 'w', encoding='utf-8') as f:
        json.dump(geojson_stops, f, ensure_ascii=False)
    print(f'站点: 写入 {len(stop_features)} 个')


if __name__ == '__main__':
    main()