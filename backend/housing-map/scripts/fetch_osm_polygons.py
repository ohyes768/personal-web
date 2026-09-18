"""
从 OpenStreetMap 获取滨江区建筑轮廓，通过坐标匹配小区数据
"""

import json
import subprocess
import time

# 滨江区边界
BINJIANG_BOUNDS = {
    'lat_min': 30.17,
    'lat_max': 30.20,
    'lon_min': 120.15,
    'lon_max': 120.21
}

def fetch_osm_buildings():
    """从 Overpass API 获取滨江区所有建筑轮廓"""
    import urllib.parse

    query = '[out:json][timeout:120];(way(30.17,120.15,30.20,120.21)[building=residential];way(30.17,120.15,30.20,120.21)[building=apartments];way(30.17,120.15,30.20,120.21)[building=yes][name~"."];);out body geom;'

    encoded = urllib.parse.quote(query)
    cmd = f'curl -s -m 180 "http://overpass-api.de/api/interpreter?data={encoded}"'

    import subprocess
    result = subprocess.run(
        cmd,
        shell=True,
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace'
    )
    output = result.stdout

    if not output:
        print('No output from OSM query')
        return []

    data = json.loads(output)
    return data.get('elements', [])


def parse_building_geometry(element: dict) -> dict:
    """解析建筑几何"""
    if element.get('type') != 'way':
        return None

    geometry = element.get('geometry', [])
    if not geometry:
        return None

    tags = element.get('tags', {})

    # 提取坐标
    coords = [[pt['lon'], pt['lat']] for pt in geometry]

    # 计算边界框
    lons = [c[0] for c in coords]
    lats = [c[1] for c in coords]
    bbox = [min(lons), min(lats), max(lons), max(lats)]

    return {
        'osm_id': element['id'],
        'name': tags.get('name', tags.get('addr:housename', '')),
        'building_type': tags.get('building', ''),
        'addr_street': tags.get('addr:street', ''),
        'addr_housenumber': tags.get('addr:housenumber', ''),
        'coords': coords,
        'bbox': bbox,
        'num_points': len(coords)
    }


def load_existing_communities():
    """加载现有小区数据"""
    import os
    data_dir = os.path.join(os.path.dirname(__file__), '..', 'data')

    with open(os.path.join(data_dir, 'binjiang_communities.json'), 'r', encoding='utf-8') as f:
        communities_raw = json.load(f)

    with open(os.path.join(data_dir, 'binjiang_coordinates.json'), 'r', encoding='utf-8') as f:
        coords_data = json.load(f)

    if isinstance(communities_raw, list):
        communities_list = communities_raw
    else:
        communities_list = communities_raw.get('communities', [])

    coords_index = {comm_id: {'latitude': v['latitude'], 'longitude': v['longitude']}
                   for comm_id, v in coords_data.items()}

    communities = []
    for c in communities_list:
        comm_id = c.get('community_id', '')
        coords = coords_index.get(comm_id, {})
        communities.append({
            'community_id': comm_id,
            'community_name': c.get('community_name', ''),
            'latitude': coords.get('latitude', 0),
            'longitude': coords.get('longitude', 0),
        })

    return communities


def match_buildings_to_communities(buildings: list[dict], communities: list[dict], threshold: float = 0.003) -> list[dict]:
    """通过坐标匹配建筑和小区"""
    matched = []

    for building in buildings:
        building_center_lon = (building['bbox'][0] + building['bbox'][2]) / 2
        building_center_lat = (building['bbox'][1] + building['bbox'][3]) / 2

        best_match = None
        best_distance = float('inf')

        for community in communities:
            comm_lon = community.get('longitude', 0)
            comm_lat = community.get('latitude', 0)

            if comm_lon == 0 or comm_lat == 0:
                continue

            distance = ((building_center_lon - comm_lon)**2 + (building_center_lat - comm_lat)**2)**0.5

            if distance < best_distance and distance < threshold:
                best_distance = distance
                best_match = community

        if best_match:
            matched.append({
                'community_id': best_match['community_id'],
                'community_name': best_match['community_name'],
                'coords': building['coords'],
                'distance': best_distance,
                'osm_id': building['osm_id'],
                'osm_name': building['name'],
            })

    return matched


def main():
    import os
    import urllib.parse

    data_dir = os.path.join(os.path.dirname(__file__), '..', 'data')

    # 加载现有小区数据
    communities = load_existing_communities()
    print(f'Loaded {len(communities)} communities')

    # 获取已有多边形（从 Shapefile）
    existing_polygons_path = os.path.join(data_dir, 'binjiang_polygons.json')
    existing_ids = set()
    if os.path.exists(existing_polygons_path):
        with open(existing_polygons_path, 'r', encoding='utf-8') as f:
            existing_data = json.load(f)
        existing_ids = set(p['community_id'] for p in existing_data.get('polygons', []))
        print(f'Existing polygons from Shapefile: {len(existing_ids)}')

    # 获取 OSM 数据
    elements = fetch_osm_buildings()
    print(f'OSM elements: {len(elements)}')

    buildings = []
    for el in elements:
        b = parse_building_geometry(el)
        if b and b['num_points'] >= 3:
            buildings.append(b)

    print(f'Buildings with geometry: {len(buildings)}')
    print(f'Buildings with name: {sum(1 for b in buildings if b["name"])}')

    # 匹配
    matched = match_buildings_to_communities(buildings, communities, threshold=0.003)
    print(f'New matches from OSM: {len(matched)}')

    # 过滤掉已有的
    new_matches = [m for m in matched if m['community_id'] not in existing_ids]
    print(f'Matches excluding existing: {len(new_matches)}')

    # 合并输出
    output = {
        'source': 'osm',
        'total_polygons': len(new_matches),
        'polygons': []
    }

    for m in new_matches:
        output['polygons'].append({
            'community_id': m['community_id'],
            'community_name': m['community_name'],
            'coords': m['coords'],
            'distance': round(m['distance'], 6),
            'osm_id': m['osm_id'],
            'osm_name': m['osm_name'],
        })

    # 保存 OSM 数据
    output_path = os.path.join(data_dir, 'binjiang_polygons_osm.json')
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f'\nSaved {len(output["polygons"])} OSM polygons to {output_path}')

    # 打印样例
    if new_matches:
        print('\nSample OSM matches:')
        for m in new_matches[:5]:
            print(f"  {m['community_name']} -> OSM:{m['osm_name']} (dist={m['distance']:.4f})")


if __name__ == '__main__':
    main()
