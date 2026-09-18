#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
抓取透明售房网小区详情页的"建筑年代"字段, 用于楼龄评分维度。

输出: data/community_ages.json  {community_id: {"name": str, "build_year": int|null, "crawled_at": str}}
支持断点续抓: 已有条目跳过。
"""
from __future__ import annotations

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
OUT_PATH = DATA_DIR / 'community_ages.json'
SLEEP_SECONDS = 2.0
BUILD_YEAR_PATTERN = re.compile(r'建筑年代[：:\s]*(\d{4})')


def extract_build_year(html_text: str) -> int | None:
    text = strip_tags(html_text)
    match = BUILD_YEAR_PATTERN.search(text)
    if not match:
        return None
    year = int(match.group(1))
    # 合理性校验: 1950-2026
    if 1950 <= year <= dt.date.today().year:
        return year
    return None


def main() -> int:
    communities_raw = json.loads((DATA_DIR / 'binjiang_communities.json').read_text(encoding='utf-8'))
    communities = communities_raw['communities'] if isinstance(communities_raw, dict) else communities_raw

    results: dict = {}
    if OUT_PATH.exists():
        results = json.loads(OUT_PATH.read_text(encoding='utf-8'))
    print(f'小区总数 {len(communities)}, 已有楼龄 {len(results)}', flush=True)

    pending = [c for c in communities if c['community_id'] not in results]
    for i, c in enumerate(pending):
        cid = c['community_id']
        url = f'{BASE_URL}/esf/xq_indexnew_{cid}.htm'
        try:
            html_text = fetch_html(url, 20)
            year = extract_build_year(html_text)
            results[cid] = {
                'name': c.get('community_name', ''),
                'build_year': year,
                'crawled_at': dt.datetime.now().isoformat(timespec='seconds'),
            }
            got = year if year else '未找到年代字段'
            print(f'[{i+1}/{len(pending)}] {c.get("community_name", cid)}: {got}', flush=True)
        except Exception as e:
            print(f'[{i+1}/{len(pending)}] {c.get("community_name", cid)}: 失败 {e}', flush=True)
            results[cid] = {'name': c.get('community_name', ''), 'build_year': None,
                            'crawled_at': dt.datetime.now().isoformat(timespec='seconds')}

        # 每 20 个保存一次进度
        if (i + 1) % 20 == 0:
            OUT_PATH.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding='utf-8')
            print(f'-- 进度已保存 ({i+1}/{len(pending)}) --', flush=True)
        time.sleep(SLEEP_SECONDS)

    OUT_PATH.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding='utf-8')
    found = sum(1 for v in results.values() if v.get('build_year'))
    print(f'完成: {len(results)} 个小区, 其中 {found} 个有建筑年代', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
