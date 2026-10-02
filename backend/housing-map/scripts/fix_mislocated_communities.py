#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
修正地理编码错位的小区坐标, 并清理其 POI 数据以便重抓。

背景: fetch_gaode_coordinates.py 用的地理编码 API 会把部分小区定位到
错误位置(甚至外市), 导致其 POI 搜索在错误位置周边进行, 带回大量区外 POI。
本脚本用高德关键字搜索(place/text, citylimit=杭州)按小区名重新定位,
校验新坐标落在覆盖范围(滨江+萧山接壤板块)外接框内才写入, 并清空对应小区的 POI 数据。
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

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.boundary import BINJIANG_BOUNDARY, XIAOSHAN_BORDER_BOUNDARIES, is_in_scope


def _scope_bbox(pad: float) -> tuple[float, float, float, float]:
    """覆盖范围 (滨江+萧山板块) 全部围栏的外接框, (lat0, lat1, lng0, lng1)"""
    pts = [p for poly in (BINJIANG_BOUNDARY, *XIAOSHAN_BORDER_BOUNDARIES.values()) for p in poly]
    lngs, lats = [p[0] for p in pts], [p[1] for p in pts]
    return (min(lats) - pad, max(lats) + pad, min(lngs) - pad, max(lngs) + pad)


CHECK_BBOX = _scope_bbox(0.02)   # 新坐标必须落在此框内才接受


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

    clat0, clat1, clng0, clng1 = CHECK_BBOX

    # 出界 = 坐标不在 scope 多边形内 (外接框判定会漏掉"失准到萧山城区中心"这类框内多边形外的点)
    mislocated = [(cid, info) for cid, info in coords.items()
                  if info.get("latitude") and not is_in_scope(info["longitude"], info["latitude"])]
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
