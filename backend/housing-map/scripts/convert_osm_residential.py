"""
将 Overpass 下载的滨江区住宅轮廓数据统一转为 GCJ-02 GeoJSON。

数据源 (均为 Overpass out geom 输出, WGS84):
- data/binjiang_osm_residential_raw.json   way[landuse=residential]  住宅用地轮廓
- data/binjiang_osm_named_buildings_raw.json  way[building][name]    带名字的建筑轮廓

输出: data/binjiang_osm_residential.geojson (GCJ-02, 供高德地图与匹配脚本使用)
properties.kind: landuse=住宅用地(围墙级,大) / building=带名建筑(楼栋级,小)
"""

import json
import math
import os

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
RAW_LANDUSE = os.path.join(DATA_DIR, 'binjiang_osm_residential_raw.json')
RAW_BUILDING = os.path.join(DATA_DIR, 'binjiang_osm_named_buildings_raw.json')
OUT_PATH = os.path.join(DATA_DIR, 'binjiang_osm_residential.geojson')


def wgs84_to_gcj02(lon: float, lat: float) -> tuple[float, float]:
    """标准 WGS84 -> GCJ-02 火星坐标转换"""
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


def to_features(raw_path: str, kind: str) -> list[dict]:
    if not os.path.exists(raw_path):
        print(f'跳过(文件不存在): {raw_path}')
        return []
    raw = json.load(open(raw_path, encoding='utf-8'))
    features = []
    for el in raw['elements']:
        geom = el.get('geometry') or []
        if len(geom) < 4 or geom[0] != geom[-1]:
            continue
        coords = [[wgs84_to_gcj02(p['lon'], p['lat']) for p in geom]]
        tags = el.get('tags', {})
        features.append({
            'type': 'Feature',
            'properties': {
                'osm_id': el['id'],
                'name': tags.get('name', ''),
                'kind': kind,
            },
            'geometry': {'type': 'Polygon', 'coordinates': coords},
        })
    return features


def main():
    features = to_features(RAW_LANDUSE, 'landuse') + to_features(RAW_BUILDING, 'building')
    landuse_n = sum(1 for f in features if f['properties']['kind'] == 'landuse')
    building_n = len(features) - landuse_n
    print(f'landuse 轮廓: {landuse_n}, 带名建筑: {building_n}, 合计: {len(features)}')

    geojson = {
        'type': 'FeatureCollection',
        '_meta': {
            'source': 'OpenStreetMap (Overpass API)',
            'coord_system': 'GCJ-02 (高德), 由 WGS84 转换',
            'feature_count': len(features),
        },
        'features': features,
    }
    with open(OUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(geojson, f, ensure_ascii=False)
    print(f'已保存 {len(features)} 个轮廓 -> data/binjiang_osm_residential.geojson')


if __name__ == '__main__':
    main()
