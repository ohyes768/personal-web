"""
将 Overpass 下载的滨江区住宅轮廓数据统一转为 GCJ-02 GeoJSON。

数据源 (均为 Overpass out geom 输出, WGS84):
- data/binjiang_osm_residential_raw.json   way[landuse=residential]  住宅用地轮廓
- data/binjiang_osm_named_buildings_raw.json  way[building][name]    带名字的建筑轮廓

输出: data/binjiang_osm_residential.geojson (GCJ-02, 供高德地图与匹配脚本使用)
properties.kind: landuse=住宅用地(围墙级,大) / building=带名建筑(楼栋级,小)
"""

import json
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.core.coordinates import transform_lat, transform_lon, wgs84_to_gcj02  # noqa: E402

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
RAW_LANDUSE = os.path.join(DATA_DIR, 'binjiang_osm_residential_raw.json')
RAW_BUILDING = os.path.join(DATA_DIR, 'binjiang_osm_named_buildings_raw.json')
OUT_PATH = os.path.join(DATA_DIR, 'binjiang_osm_residential.geojson')


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
