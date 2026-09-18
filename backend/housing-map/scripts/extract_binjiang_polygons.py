"""
从 Shapefile 提取滨江区小区轮廓，与现有小区数据匹配
"""

import struct
import json
from pathlib import Path

# 滨江区边界 (近似)
BINJIANG_BOUNDS = {
    'lat_min': 30.17, 'lat_max': 30.20,
    'lon_min': 120.15, 'lon_max': 120.20
}

def read_shp_polygons(shp_path: str) -> list[dict]:
    """读取 SHP 文件中的所有多边形"""
    polygons = []

    with open(shp_path, 'rb') as f:
        data = f.read()

    offset = 100  # Skip 100-byte header
    while offset < len(data) - 12:
        try:
            rec_num = struct.unpack('>I', data[offset:offset+4])[0]
            content_len = struct.unpack('>I', data[offset+4:offset+8])[0]
            shape_type = struct.unpack('<I', data[offset+8:offset+12])[0]

            if shape_type != 5:  # Not a polygon
                offset += 8 + content_len * 2
                continue

            box_offset = offset + 12
            x_min = struct.unpack('<d', data[box_offset:box_offset+8])[0]
            y_min = struct.unpack('<d', data[box_offset+8:box_offset+16])[0]
            x_max = struct.unpack('<d', data[box_offset+16:box_offset+24])[0]
            y_max = struct.unpack('<d', data[box_offset+24:box_offset+32])[0]

            num_parts = struct.unpack('<i', data[box_offset+32:box_offset+36])[0]
            num_points = struct.unpack('<i', data[box_offset+36:box_offset+40])[0]

            # Read parts array
            parts_offset = box_offset + 40
            part_starts = []
            for i in range(num_parts):
                part_start = struct.unpack('<i', data[parts_offset+i*4:parts_offset+i*4+4])[0]
                part_starts.append(part_start)
            part_starts.append(num_points)  # End marker

            # Read points for each part
            points_offset = parts_offset + num_parts * 4
            coords = []
            for i in range(num_points):
                x = struct.unpack('<d', data[points_offset+i*16:points_offset+i*16+8])[0]
                y = struct.unpack('<d', data[points_offset+i*16+8:points_offset+i*16+16])[0]
                coords.append([x, y])  # [lon, lat] for GeoJSON

            polygons.append({
                'record_id': rec_num,
                'bbox': [x_min, y_min, x_max, y_max],
                'num_points': num_points,
                'coords': coords
            })

            offset += 8 + content_len * 2

        except Exception as e:
            print(f"Error at offset {offset}: {e}")
            break

    return polygons


def filter_binjiang_polygons(polygons: list[dict]) -> list[dict]:
    """筛选滨江区内的多边形"""
    filtered = []
    for p in polygons:
        bbox = p['bbox']
        x_min, y_min, x_max, y_max = bbox

        # Check if polygon intersects with Binjiang bounds
        if (y_max >= BINJIANG_BOUNDS['lat_min'] and y_min <= BINJIANG_BOUNDS['lat_max'] and
            x_max >= BINJIANG_BOUNDS['lon_min'] and x_min <= BINJIANG_BOUNDS['lon_max']):
            filtered.append(p)

    return filtered


def load_existing_communities(communities_path: str, coords_path: str) -> list[dict]:
    """加载现有小区数据和坐标"""
    with open(communities_path, 'r', encoding='utf-8') as f:
        communities_raw = json.load(f)

    with open(coords_path, 'r', encoding='utf-8') as f:
        coords_data = json.load(f)

    # Build communities with coordinates
    if isinstance(communities_raw, list):
        communities_list = communities_raw
    elif isinstance(communities_raw, dict) and 'communities' in communities_raw:
        communities_list = communities_raw['communities']
    else:
        communities_list = []

    # Index coordinates by community_id
    coords_index = {}
    for comm_id, coord_info in coords_data.items():
        coords_index[comm_id] = {
            'latitude': coord_info.get('latitude', 0),
            'longitude': coord_info.get('longitude', 0)
        }

    # Merge
    communities = []
    for c in communities_list:
        comm_id = c.get('community_id', '')
        coords = coords_index.get(comm_id, {})
        communities.append({
            'community_id': comm_id,
            'community_name': c.get('community_name', ''),
            'latitude': coords.get('latitude', 0) or c.get('latitude', 0),
            'longitude': coords.get('longitude', 0) or c.get('longitude', 0),
        })

    return communities


def match_polygons_to_communities(polygons: list[dict], communities: list[dict], threshold: float = 0.001) -> list[dict]:
    """通过坐标匹配多边形和小区的中心点"""
    matched = []

    for polygon in polygons:
        polygon_center_lon = (polygon['bbox'][0] + polygon['bbox'][2]) / 2
        polygon_center_lat = (polygon['bbox'][1] + polygon['bbox'][3]) / 2

        best_match = None
        best_distance = float('inf')

        for community in communities:
            comm_lon = community.get('longitude', 0)
            comm_lat = community.get('latitude', 0)

            if comm_lon == 0 or comm_lat == 0:
                continue

            # Calculate distance
            distance = ((polygon_center_lon - comm_lon)**2 + (polygon_center_lat - comm_lat)**2)**0.5

            if distance < best_distance and distance < threshold:
                best_distance = distance
                best_match = community

        if best_match:
            matched.append({
                'community_id': best_match.get('community_id', ''),
                'community_name': best_match.get('community_name', ''),
                'polygon': polygon,
                'distance': best_distance
            })

    return matched


def main():
    base_dir = Path(__file__).parent.parent
    data_dir = base_dir / 'data'
    extract_dir = data_dir / '_temp_extract'

    # 读取现有小区数据（含坐标）
    communities_path = data_dir / 'binjiang_communities.json'
    coords_path = data_dir / 'binjiang_coordinates.json'
    communities = load_existing_communities(str(communities_path), str(coords_path))
    print(f"Loaded {len(communities)} communities")

    # Count valid coordinates
    valid_coords = sum(1 for c in communities if c.get('latitude') and c.get('longitude'))
    print(f"Communities with valid coordinates: {valid_coords}")

    # 读取 Shapefile
    shp_path = extract_dir / 'Hangzhou_202302.shp'
    all_polygons = read_shp_polygons(str(shp_path))
    print(f"Total polygons in Shapefile: {len(all_polygons)}")

    # 筛选滨江区
    binjiang_polygons = filter_binjiang_polygons(all_polygons)
    print(f"Polygons in Binjiang: {len(binjiang_polygons)}")

    # 匹配 (增大阈值，因为多边形边界可能比中心点更远)
    matched = match_polygons_to_communities(binjiang_polygons, communities, threshold=0.005)
    print(f"Matched to communities: {len(matched)}")

    # 输出结果
    output = {
        'total_polygons': len(binjiang_polygons),
        'matched_count': len(matched),
        'polygons': []
    }

    for m in matched:
        output['polygons'].append({
            'community_id': m['community_id'],
            'community_name': m['community_name'],
            'coords': m['polygon']['coords'],
            'distance': round(m['distance'], 6)
        })

    # 保存
    output_path = data_dir / 'binjiang_polygons.json'
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\nSaved {len(output['polygons'])} polygons to {output_path}")

    # 打印匹配样例
    print("\nSample matched polygons:")
    for m in matched[:3]:
        print(f"  {m['community_name']}: {len(m['polygon']['coords'])} points, distance={m['distance']:.6f}")


if __name__ == '__main__':
    main()
