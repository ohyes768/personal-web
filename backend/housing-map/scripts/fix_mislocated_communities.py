#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
修正地理编码错位的小区坐标, 并清理其 POI 数据以便重抓。

背景: fetch_gaode_coordinates.py 用的地理编码 API 会把部分小区定位到
错误位置(甚至外市), 导致其 POI 搜索在错误位置周边进行, 带回大量区外 POI。
本脚本用高德关键字搜索(place/text, citylimit=杭州)按小区名重新定位,
校验新坐标落在滨江区附近后才写入, 并清空对应小区的 POI 数据。
之后运行: python scripts/fetch_gaode_pois.py --only subway school hospital mall park bus
即可只重抓这些小区(其余小区已有数据会被 --only 逻辑跳过)。
"""
from __future__ import annotations

import json
import re
import sys
import io
import time
import urllib.parse
import urllib.request
from pathlib import Path

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

try:
    from _gaode_config import GAODE_API_KEY  # gitignored, 见 _gaode_config.py
except ImportError:
    GAODE_API_KEY = ""  # 未配置: 请创建 scripts/_gaode_config.py

# 滨江区 bbox(Nominatim), 修正校验用放宽一点的框
BINJIANG_BBOX = (30.1387, 30.2390, 120.1176, 120.2321)
CHECK_BBOX = (30.13, 30.25, 120.10, 120.30)   # 新坐标必须落在此框内才接受


def search_poi(name: str) -> tuple[float, float] | None:
    """关键字搜索小区, 返回第一个结果的坐标"""
    params = urllib.parse.urlencode({
        "key": GAODE_API_KEY,
        "keywords": name,
        "city": "杭州",
        "citylimit": "true",
        "offset": 5,
    })
    url = f"https://restapi.amap.com/v3/place/text?{params}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "housingmap/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if data.get("status") == "1" and data.get("pois"):
            location = data["pois"][0].get("location", "")
            m = re.match(r"^([\d.]+),([\d.]+)$", location)
            if m:
                return float(m.group(1)), float(m.group(2))  # lng, lat
    except Exception as e:
        print(f"    x 搜索失败: {e}")
    return None


def main():
    data_dir = Path(__file__).parent.parent / "data"
    coords_path = data_dir / "binjiang_coordinates.json"
    pois_path = data_dir / "binjiang_pois.json"

    coords = json.loads(coords_path.read_text(encoding="utf-8"))
    pois = json.loads(pois_path.read_text(encoding="utf-8"))

    lat0, lat1, lng0, lng1 = BINJIANG_BBOX
    clat0, clat1, clng0, clng1 = CHECK_BBOX

    mislocated = [(cid, info) for cid, info in coords.items()
                  if info.get("latitude") and not (lat0 <= info["latitude"] <= lat1 and lng0 <= info["longitude"] <= lng1)]
    print(f"坐标出界的小区: {len(mislocated)} 个\n")

    fixed, failed = [], []
    for cid, info in mislocated:
        name = info["name"]
        print(f"[{name}] ({info['latitude']:.4f},{info['longitude']:.4f})", flush=True)
        result = search_poi(name)
        time.sleep(0.15)
        if result is None:
            print("    x 搜索无结果, 保留原坐标")
            failed.append(name)
            continue
        lng, lat = result
        if not (clat0 <= lat <= clat1 and clng0 <= lng <= clng1):
            print(f"    x 新坐标仍出框 ({lat:.4f},{lng:.4f}), 保留原坐标")
            failed.append(name)
            continue
        old = (info["latitude"], info["longitude"])
        coords[cid] = {**info, "latitude": lat, "longitude": lng}
        # 清空该小区 POI, 供 fetch_gaode_pois.py --only 重抓
        if cid in pois:
            pois[cid] = {"name": name, "pois": {}}
        fixed.append((name, old, (lat, lng)))
        print(f"    -> ({lat:.4f},{lng:.4f})")

    coords_path.write_text(json.dumps(coords, ensure_ascii=False, indent=2), encoding="utf-8")
    pois_path.write_text(json.dumps(pois, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n修正 {len(fixed)} 个, 失败 {len(failed)} 个: {failed}")
    print("下一步: python scripts/fetch_gaode_pois.py --only subway school hospital mall park bus")


if __name__ == "__main__":
    main()
