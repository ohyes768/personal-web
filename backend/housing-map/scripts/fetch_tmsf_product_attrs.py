#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
抓取透明售房网小区详情页的产品力字段: 车位数/总户数/物业费/建筑面积。

输出: data/community_attrs.json
  {community_id: {"name": str, "parking_spots": int|null, "households": int|null,
                  "property_fee": float|null, "gross_area_sqm": int|null,
                  "far_ratio": float|null, "greening_rate": float|null, "crawled_at": str}}
车位比 = parking_spots / households (展示/评分时计算)。
支持断点续抓: 已有条目跳过; --refresh 强制全部重抓并合并新字段。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import io
import time
from pathlib import Path

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

sys.path.insert(0, str(Path(__file__).parent))
from fetch_tmsf_price_snapshot import fetch_html, strip_tags, BASE_URL

DATA_DIR = Path(__file__).parent.parent / 'data'
OUT_PATH = DATA_DIR / 'community_attrs.json'
SLEEP_SECONDS = 1.5

PATTERNS = {
    'parking_spots': re.compile(r'车\s*位\s*数[:：\s]*(\d+)'),
    'households': re.compile(r'总\s*户\s*数[:：\s]*(\d+)'),
    'property_fee': re.compile(r'物业费用[:：\s]*([\d.]+)\s*元'),
    'gross_area_sqm': re.compile(r'建筑面积[:：\s]*([\d,]+)\s*平米'),
    'far_ratio': re.compile(r'容\s*积\s*率[:：\s]*([\d.]+)'),
    'greening_rate': re.compile(r'绿\s*化\s*率[:：\s]*([\d.]+)\s*%'),
}


def extract_attrs(html_text: str) -> dict:
    text = strip_tags(html_text)
    attrs: dict = {}
    for key, pattern in PATTERNS.items():
        m = pattern.search(text)
        if m:
            value = m.group(1).replace(',', '')
            try:
                num = float(value)
                attrs[key] = int(num) if num == int(num) and key != 'property_fee' else round(num, 2)
            except ValueError:
                pass
    return attrs


def main() -> int:
    parser = argparse.ArgumentParser(description='抓取小区产品力属性')
    parser.add_argument('--refresh', action='store_true', help='重抓全部小区并合并新字段(默认跳过已有)')
    args = parser.parse_args()

    communities_raw = json.loads((DATA_DIR / 'binjiang_communities.json').read_text(encoding='utf-8'))
    communities = communities_raw['communities'] if isinstance(communities_raw, dict) else communities_raw

    results: dict = {}
    if OUT_PATH.exists():
        results = json.loads(OUT_PATH.read_text(encoding='utf-8'))
    mode = '全量重抓(合并)' if args.refresh else '断点续抓'
    print(f'小区总数 {len(communities)}, 已有 {len(results)}, 模式: {mode}', flush=True)

    pending = communities if args.refresh else [c for c in communities if c['community_id'] not in results]
    for i, c in enumerate(pending):
        cid = c['community_id']
        url = f'{BASE_URL}/esf/xq_indexnew_{cid}.htm'
        try:
            html_text = fetch_html(url, 20)
            attrs = extract_attrs(html_text)
            results[cid] = {**results.get(cid, {}), 'name': c.get('community_name', ''),
                            **attrs, 'crawled_at': dt.datetime.now().isoformat(timespec='seconds')}
            brief = ' '.join(f'{k}={v}' for k, v in attrs.items()) or '无产品字段'
            print(f'[{i+1}/{len(pending)}] {c.get("community_name", cid)}: {brief}', flush=True)
        except Exception as e:
            print(f'[{i+1}/{len(pending)}] {c.get("community_name", cid)}: 失败 {type(e).__name__}', flush=True)

        if (i + 1) % 25 == 0:
            OUT_PATH.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding='utf-8')
            print(f'-- 进度已保存 ({i+1}/{len(pending)}) --', flush=True)
        time.sleep(SLEEP_SECONDS)

    OUT_PATH.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding='utf-8')
    has_parking = sum(1 for v in results.values() if v.get('parking_spots') and v.get('households'))
    has_fee = sum(1 for v in results.values() if v.get('property_fee'))
    print(f'完成: {len(results)} 个, 可算车位比 {has_parking}, 有物业费 {has_fee}', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
