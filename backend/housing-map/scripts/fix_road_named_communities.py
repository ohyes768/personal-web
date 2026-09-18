"""
修复透明售房网"路名归组"伪小区:

规则(2026-09-15 与用户确认: B 优先, 没救的走 A):
- B: 路名/村名条目若有可用别名(alias != 名称, 且别名本身不是路名),
     改用别名作为小区名并重新地理编码, 原名称换到 alias 字段保留溯源
- A: 无可用别名 且 无价格记录 的条目直接删除(纯噪音: 无价格无在售, 定位在马路上)
- 其余(无别名但有价格)保留原样 —— 点落在路上, 对"按路归组的散盘价格桶"反而语义正确

注意: 名称以"新村"结尾的是真小区(如马湖新村), 不在处理范围。
改前备份 communities/coordinates 两个 JSON 为 .bak。

输入输出(就地更新):
- data/binjiang_communities.json
- data/binjiang_coordinates.json
"""

import json
import re
import shutil
import time
import urllib.parse
import urllib.request
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / 'data'
COMM_PATH = DATA_DIR / 'binjiang_communities.json'
COORD_PATH = DATA_DIR / 'binjiang_coordinates.json'
SNAPSHOT_PATH = DATA_DIR / 'price_snapshots.jsonl'

try:
    from _gaode_config import GAODE_API_KEY  # gitignored, 见 _gaode_config.py
except ImportError:
    GAODE_API_KEY = ""  # 未配置: 请创建 scripts/_gaode_config.py

ROAD_SUFFIX_RE = re.compile(r'(路|街|大道|弄|巷|桥|站)$')


def is_road_named(name: str) -> bool:
    """路名/村名判定; 排除'新村'(真小区后缀)"""
    if name.endswith('村') and not name.endswith('新村'):
        return True
    return bool(ROAD_SUFFIX_RE.search(name))


def has_useful_alias(name: str, alias: str | None) -> bool:
    if not alias or alias == name:
        return False
    return not is_road_named(alias)


def geocode(alias: str) -> dict | None:
    """高德地理编码: 返回 {longitude, latitude, formatted_address} 或 None"""
    params = urllib.parse.urlencode({
        'key': GAODE_API_KEY,
        'address': f'杭州市滨江区{alias}',
        'city': '杭州',
    })
    try:
        req = urllib.request.Request(f'https://restapi.amap.com/v3/geocode/geo?{params}')
        data = json.loads(urllib.request.urlopen(req, timeout=10).read().decode('utf-8'))
        if data.get('status') == '1' and data.get('geocodes'):
            g = data['geocodes'][0]
            location = g['location'].split(',')
            return {
                'longitude': float(location[0]),
                'latitude': float(location[1]),
                'formatted_address': g.get('formatted_address', ''),
            }
    except Exception as e:
        print(f'    地理编码失败: {e}')
    return None


def main():
    communities = json.load(open(COMM_PATH, encoding='utf-8'))
    wrapped = isinstance(communities, dict)
    comm_list = communities['communities'] if wrapped else communities
    coords = json.load(open(COORD_PATH, encoding='utf-8'))

    priced_ids = set()
    for line in open(SNAPSHOT_PATH, encoding='utf-8'):
        line = line.strip()
        if line:
            priced_ids.add(json.loads(line)['community_id'])

    renamed, removed, kept, geocode_failed = [], [], [], []

    for c in comm_list:
        name = c.get('community_name', '')
        cid = c['community_id']
        if not is_road_named(name):
            continue

        alias = c.get('community_alias')
        if has_useful_alias(name, alias):
            # B: 改名 + 重新地理编码
            print(f'B 改名: {name} -> {alias}')
            result = geocode(alias)
            if result and alias in result['formatted_address']:
                c['community_name'], c['community_alias'] = alias, name
                coords[cid] = {'name': alias, **result}
                renamed.append((name, alias, result['formatted_address']))
            else:
                print(f'  地理编码未命中真实楼盘(返回: {result["formatted_address"] if result else "无"}), 保留原样')
                geocode_failed.append(name)
                kept.append(name)
            time.sleep(0.2)
        elif cid not in priced_ids:
            # A: 无别名无价格 -> 删除
            print(f'A 删除: {name} (无别名, 无价格)')
            removed.append(name)
            coords.pop(cid, None)
        else:
            kept.append(name)

    if removed:
        removed_ids = {c['community_id'] for c in comm_list if c['community_name'] in removed}
        comm_list = [c for c in comm_list if c['community_id'] not in removed_ids]

    # 备份并写回
    shutil.copy2(COMM_PATH, str(COMM_PATH) + '.bak')
    shutil.copy2(COORD_PATH, str(COORD_PATH) + '.bak')
    json.dump(communities if wrapped else comm_list,
              open(COMM_PATH, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    json.dump(coords, open(COORD_PATH, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)

    print(f'\n=== 汇总 ===')
    print(f'B 改名+重定位: {len(renamed)} 个')
    for old, new, addr in renamed:
        print(f'  {old} -> {new} ({addr})')
    print(f'A 删除: {len(removed)} 个: {", ".join(removed)}')
    print(f'保留(有价格的路名归组/地理编码未命中): {len(kept)} 个: {", ".join(kept)}')
    print(f'小区总数: {len(comm_list)}')


if __name__ == '__main__':
    main()
