#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""拉取萧山接壤街道边界 (Nominatim, WGS-84) 转 GCJ-02, 输出可粘贴进 boundary.py 的字面量。

用法:
    python scripts/fetch_street_boundaries.py           # 拉取并打印抽稀后的 Python 字面量
    python scripts/fetch_street_boundaries.py --raw     # 附带打印原始点数

坐标系: Nominatim/OSM 为 WGS-84, 项目围栏为 GCJ-02 (高德), 转换复用
        convert_osm_transit.wgs84_to_gcj02。
抽稀: Douglas-Peucker (epsilon 度)。裁剪用途 1e-4 度 (~10m) 精度足够。
"""

from __future__ import annotations

import argparse
import io
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from convert_osm_transit import wgs84_to_gcj02  # noqa: E402

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# 萧山接壤滨江的板块 (parent PRD 2026-10-02 确认: 盈丰/宁围/闻堰)
STREETS = ["闻堰街道", "宁围街道", "盈丰街道"]
UA = "housingmap-research/1.0"
EPSILON = 1e-4  # DP 抽稀容差 (度)


def fetch_boundary(name: str) -> list[list[float]]:
    """Nominatim 搜索单个街道, 返回 WGS-84 外环 [[lng, lat], ...]"""
    query = urllib.parse.quote(f"{name},杭州")
    url = (
        f"https://nominatim.openstreetmap.org/search?q={query}"
        f"&format=json&polygon_geojson=1&limit=1&countrycodes=cn"
    )
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    results = json.loads(urllib.request.urlopen(req, timeout=30).read().decode())
    if not results:
        raise RuntimeError(f"Nominatim 无结果: {name}")
    geo = results[0].get("geojson") or {}
    if geo.get("type") != "Polygon":
        raise RuntimeError(f"{name} 非 Polygon: {geo.get('type')}")
    return geo["coordinates"][0]  # 外环


def to_gcj02(ring: list[list[float]]) -> list[list[float]]:
    return [[*wgs84_to_gcj02(lon, lat)] for lon, lat in ring]


def douglas_peucker(points: list[list[float]], eps: float) -> list[list[float]]:
    """递归 DP 抽稀; 首尾必留。输入输出同形 [[lng, lat], ...]"""
    if len(points) < 3:
        return points

    def perpendicular_distance(pt, start, end) -> float:
        (x, y), (x1, y1), (x2, y2) = pt, start, end
        dx, dy = x2 - x1, y2 - y1
        if dx == 0 and dy == 0:
            return ((x - x1) ** 2 + (y - y1) ** 2) ** 0.5
        t = ((x - x1) * dx + (y - y1) * dy) / (dx * dx + dy * dy)
        px, py = x1 + t * dx, y1 + t * dy
        return ((x - px) ** 2 + (y - py) ** 2) ** 0.5

    dmax, index = 0.0, 0
    for i in range(1, len(points) - 1):
        d = perpendicular_distance(points[i], points[0], points[-1])
        if d > dmax:
            index, dmax = i, d
    if dmax > eps:
        left = douglas_peucker(points[: index + 1], eps)
        right = douglas_peucker(points[index:], eps)
        return left[:-1] + right
    return [points[0], points[-1]]


def ensure_closed(ring: list[list[float]]) -> list[list[float]]:
    if ring[0] != ring[-1]:
        ring = [*ring, ring[0]]
    return ring


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", action="store_true", help="附带打印原始点数")
    args = parser.parse_args()

    lines = []
    for name in STREETS:
        ring_wgs = fetch_boundary(name)
        ring_gcj = to_gcj02(ring_wgs)
        simplified = douglas_peucker(ensure_closed(ring_gcj), EPSILON)
        key = name.replace("街道", "")
        lines.append(f'    "{key}": [')
        for i in range(0, len(simplified), 4):
            chunk = simplified[i : i + 4]
            lines.append("        " + " ".join(f"[{p[0]:.6f}, {p[1]:.6f}]," for p in chunk))
        lines.append("    ],")
        raw_note = f", 原始 {len(ring_wgs)} 点" if args.raw else ""
        print(f"# {name}: 抽稀后 {len(simplified)} 点{raw_note}", file=sys.stderr)
        time.sleep(1.5)  # Nominatim 用法约定: 串行 >= 1s

    print("XIAOSHAN_BORDER_BOUNDARIES: dict[str, list[list[float]]] = {")
    print("\n".join(lines))
    print("}")


if __name__ == "__main__":
    main()
