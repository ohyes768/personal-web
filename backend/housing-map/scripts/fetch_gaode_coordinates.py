#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
获取滨江区小区坐标
通过高德地理编码 API 将小区地址转换为经纬度坐标
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
GAODE_API_URL = "https://restapi.amap.com/v3/geocode/geo"

def load_communities():
    """加载小区列表"""
    data_file = Path(__file__).parent.parent / "data" / "binjiang_communities.json"
    if not data_file.exists():
        print(f"错误: 找不到小区数据文件 {data_file}")
        sys.exit(1)

    with open(data_file, "r", encoding="utf-8") as f:
        return json.load(f)

def fetch_coordinates(communities: list) -> dict:
    """批量获取小区坐标"""
    results = {}
    total = len(communities)
    failed = []

    for i, community in enumerate(communities):
        name = community.get("community_name") or community.get("name")
        community_id = community.get("community_id") or community.get("id")
        # 构造地址：杭州市滨江区+小区名
        address = f"杭州市滨江区{name}"

        print(f"[{i+1}/{total}] {name}", flush=True)

        # 调用高德地理编码 API
        import urllib.request
        import urllib.parse

        params = urllib.parse.urlencode({
            "key": GAODE_API_KEY,
            "address": address,
            "city": "杭州",
        })

        url = f"{GAODE_API_URL}?{params}"

        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode("utf-8"))

            if data.get("status") == "1" and data.get("geocodes"):
                location = data["geocodes"][0]["location"].split(",")
                results[community_id] = {
                    "name": name,
                    "longitude": float(location[0]),
                    "latitude": float(location[1]),
                    "formatted_address": data["geocodes"][0].get("formatted_address", ""),
                }
                print(f"  -> {location[0]}, {location[1]}", flush=True)
            else:
                failed.append({"id": community_id, "name": name, "reason": data.get('info', 'unknown')})
                print(f"  x {data.get('info', 'unknown')}", flush=True)

        except Exception as e:
            failed.append({"id": community_id, "name": name, "reason": str(e)})
            print(f"  x {e}", flush=True)

        # 控制请求频率
        if i < total - 1:
            time.sleep(0.15)

    print(f"\n成功: {len(results)}, 失败: {len(failed)}")
    if failed:
        print("失败列表:")
        for f_item in failed[:10]:
            print(f"  - {f_item['name']}: {f_item['reason']}")
        if len(failed) > 10:
            print(f"  ... 还有 {len(failed) - 10} 个")

    return results

def main():
    print("=" * 50)
    print("滨江区小区坐标获取")
    print("=" * 50)

    # 加载小区数据
    communities = load_communities()
    print(f"共 {len(communities)} 个小区\n")

    # 获取坐标
    results = fetch_coordinates(communities)

    # 保存结果
    output_file = Path(__file__).parent.parent / "data" / "binjiang_coordinates.json"
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n结果已保存到: {output_file}")

if __name__ == "__main__":
    main()