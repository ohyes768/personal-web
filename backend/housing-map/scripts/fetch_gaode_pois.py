#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
获取滨江区小区周边 POI 数据
通过高德 POI 查询 API 获取周边设施（学校、医院、地铁站、商场、公园、公交站）
"""
from __future__ import annotations

import json
import time
import sys
import io
from pathlib import Path

# Windows 控制台编码修复
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# 高德 API Key
try:
    from _gaode_config import GAODE_API_KEY  # gitignored, 见 _gaode_config.py
except ImportError:
    GAODE_API_KEY = ""  # 未配置: 请创建 scripts/_gaode_config.py
GAODE_API_URL = "https://restapi.amap.com/v3/place/around"

# POI 类型配置（高德类型码）
# 注意: school 旧码 150600 实为收费站、bus 旧码 150200 查不到数据, 2026-09-15 修正
POI_TYPES = {
    "subway": ("150500", "地铁站", 800),
    "school": ("141200", "学校", 1500),
    "hospital": ("090100", "医院", 2000),
    "mall": ("060101", "商场", 1500),
    "park": ("110101", "公园", 1500),
    "bus": ("150700", "公交站", 500),
}

def load_coordinates():
    """加载小区坐标"""
    coord_file = Path(__file__).parent.parent / "data" / "binjiang_coordinates.json"
    if not coord_file.exists():
        print(f"错误: 找不到坐标文件 {coord_file}")
        print("请先运行 fetch_gaode_coordinates.py 获取坐标")
        sys.exit(1)

    with open(coord_file, "r", encoding="utf-8") as f:
        return json.load(f)

def fetch_pois_for_community(community_id: str, name: str, lat: float, lng: float, types_dict: dict) -> dict:
    """获取单个小区周边所有 POI"""
    results = {}

    for poi_type, (type_code, type_name, radius) in types_dict.items():
        print(f"    [{type_name}] radius{radius}m", flush=True)

        import urllib.request
        import urllib.parse

        params = urllib.parse.urlencode({
            "key": GAODE_API_KEY,
            "location": f"{lng},{lat}",
            "types": type_code,
            "radius": radius,
            "offset": 60,
            "page": 1,
            "extensions": "all",
        })

        url = f"{GAODE_API_URL}?{params}"

        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode("utf-8"))

            pois = []
            if data.get("status") == "1" and data.get("pois"):
                for poi in data["pois"]:
                    location = poi.get("location", "").split(",")
                    if len(location) == 2:
                        pois.append({
                            "name": poi.get("name", ""),
                            "type": poi_type,
                            "type_name": type_name,
                            "distance": int(poi.get("distance", 0)),
                            "longitude": float(location[0]),
                            "latitude": float(location[1]),
                            "address": poi.get("address", ""),
                        })

            results[poi_type] = pois
            print(f"      -> found {len(pois)}", flush=True)

        except Exception as e:
            print(f"      x error: {e}", flush=True)
            results[poi_type] = []

        time.sleep(0.12)

    return results

def main():
    import argparse
    parser = argparse.ArgumentParser(description='抓取小区周边 POI')
    parser.add_argument('--only', nargs='*', choices=list(POI_TYPES),
                        help='只抓指定类型(增量补抓: 跳过已有非空数据的类型, 其余类型保留原数据)')
    parser.add_argument('--max', type=int, default=0, help='最多处理 N 个小区(0=全部, 用于小批验证)')
    args = parser.parse_args()

    print("=" * 50)
    print("POI Data Fetcher for Binjiang Communities")
    print("=" * 50)

    types_to_fetch = {k: v for k, v in POI_TYPES.items() if not args.only or k in args.only}

    coordinates = load_coordinates()
    output_file = Path(__file__).parent.parent / "data" / "binjiang_pois.json"

    all_pois = {}
    if output_file.exists():
        with open(output_file, encoding='utf-8') as f:
            all_pois = json.load(f)

    items = list(coordinates.items())
    if args.max:
        items = items[:args.max]
    print(f"Communities: {len(coordinates)}, types: {list(types_to_fetch)}\n")

    done = 0
    for i, (community_id, info) in enumerate(items):
        if args.only:
            existing = all_pois.get(community_id, {}).get('pois', {})
            if all(existing.get(t) for t in args.only):
                continue

        print(f"[{i+1}/{len(items)}] {info['name']}", flush=True)
        pois = fetch_pois_for_community(
            community_id,
            info["name"],
            info["latitude"],
            info["longitude"],
            types_to_fetch
        )
        merged = all_pois.get(community_id, {}).get('pois', {})
        merged.update(pois)
        all_pois[community_id] = {
            "name": info["name"],
            "pois": merged,
        }
        done += 1

        # 每 50 个保存一次进度
        if done % 50 == 0:
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(all_pois, f, ensure_ascii=False, indent=2)
            print(f"\nProgress saved ({done} fetched)\n", flush=True)

        time.sleep(0.2)

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(all_pois, f, ensure_ascii=False, indent=2)

    print(f"\nDone! Fetched {done} communities. Saved to: {output_file}")

if __name__ == "__main__":
    main()