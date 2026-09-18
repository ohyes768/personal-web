#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
按图层下载滨江区 OSM 数据 (Overpass API), 原始 JSON 存 data/ 供后续使用。

用法:
    python scripts/fetch_osm_layers.py green water pois roads transit_routes transit_stops
    python scripts/fetch_osm_layers.py          # 全部图层

图层说明:
    green           公园绿地 (leisure/landuse/natural)
    water           水系 (natural=water, waterway)
    pois            POI 全量 (amenity/shop/healthcare/education/tourism/office/craft, out center)
    roads           道路网 (highway, out geom)
    transit_routes  公交地铁线路 (relation route=bus/subway/tram/train/ferry, out geom)
    transit_stops   站点 (bus_stop / public_transport, out center)
"""

from __future__ import annotations

import json
import re
import sys
import io
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

BBOX = '30.1387,120.1176,30.2390,120.2321'  # 滨江区
OVERPASS_URL = 'https://overpass-api.de/api/interpreter'
DATA_DIR = Path(__file__).parent.parent / 'data'

LAYERS: dict[str, dict] = {
    'green': {
        'query': f'''[out:json][timeout:180];
(
  way({BBOX})[leisure~"^(park|garden|pitch|playground|sports_centre|track|fitness_station)$"];
  relation({BBOX})[leisure~"^(park|garden|pitch|playground|sports_centre|track)$"];
  way({BBOX})[landuse~"^(grass|forest|meadow|recreation_ground|village_green)$"];
  relation({BBOX})[landuse~"^(grass|forest|meadow|recreation_ground|village_green)$"];
  way({BBOX})[natural~"^(wood|scrub|grassland)$"];
  relation({BBOX})[natural~"^(wood|scrub|grassland)$"];
);
out geom;''',
        'out': 'binjiang_osm_green_raw.json',
    },
    'water': {
        'query': f'''[out:json][timeout:180];
(
  way({BBOX})[natural=water];
  relation({BBOX})[natural=water];
  way({BBOX})[waterway];
  relation({BBOX})[waterway];
);
out geom;''',
        'out': 'binjiang_osm_water_raw.json',
    },
    'pois': {
        'query': f'''[out:json][timeout:180];
(
  node({BBOX})[amenity];
  way({BBOX})[amenity];
  node({BBOX})[shop];
  way({BBOX})[shop];
  node({BBOX})[healthcare];
  node({BBOX})[education];
  node({BBOX})[tourism];
  way({BBOX})[tourism];
  node({BBOX})[office];
  node({BBOX})[craft];
  node({BBOX})[leisure~"^(fitness_centre|sports_centre|stadium|swimming_pool)$"];
);
out center;''',
        'out': 'binjiang_osm_pois_raw.json',
    },
    'roads': {
        'query': f'''[out:json][timeout:180];
way({BBOX})[highway];
out geom;''',
        'out': 'binjiang_osm_roads_raw.json',
    },
    'transit_routes': {
        'query': f'''[out:json][timeout:180];
relation({BBOX})[route~"^(bus|subway|tram|train|ferry)$"];
out geom;''',
        'out': 'binjiang_osm_transit_routes_raw.json',
    },
    'transit_stops': {
        'query': f'''[out:json][timeout:180];
(
  node({BBOX})[highway=bus_stop];
  node({BBOX})[public_transport~"^(stop_position|platform|station)$"];
  way({BBOX})[public_transport=platform];
  node({BBOX})[railway~"^(station|halt|tram_stop)$"];
);
out center;''',
        'out': 'binjiang_osm_transit_stops_raw.json',
    },
}


def fetch(query: str, tries: int = 3) -> dict | None:
    for attempt in range(1, tries + 1):
        try:
            data = urllib.parse.urlencode({'data': query}).encode()
            req = urllib.request.Request(OVERPASS_URL, data=data, headers={'User-Agent': 'housingmap-research/1.0'})
            return json.loads(urllib.request.urlopen(req, timeout=180).read().decode())
        except urllib.error.HTTPError as e:
            body = re.sub(r'<[^>]+>', ' ', e.read().decode())
            msg = re.sub(r'\s+', ' ', body)[-80:]
            print(f'    HTTP {e.code} (第{attempt}次): {msg}', flush=True)
        except Exception as e:
            print(f'    {e} (第{attempt}次)', flush=True)
        if attempt < tries:
            time.sleep(45)
    return None


def summarize(result: dict) -> str:
    els = result.get('elements', [])
    kinds = Counter(el['type'] for el in els)
    named = sum(1 for el in els if el.get('tags', {}).get('name'))
    main_tags = Counter()
    for el in els:
        t = el.get('tags', {})
        for key in ('leisure', 'landuse', 'natural', 'waterway', 'amenity', 'shop', 'healthcare',
                    'education', 'tourism', 'office', 'highway', 'route', 'railway', 'public_transport'):
            if key in t:
                main_tags[f'{key}={t[key]}'] += 1
                break
    top = ', '.join(f'{k}:{v}' for k, v in main_tags.most_common(6))
    return f'{len(els)} 要素 ({dict(kinds)}), 带名 {named}  | 主要标签: {top}'


def main() -> None:
    wanted = sys.argv[1:] or list(LAYERS)
    unknown = [w for w in wanted if w not in LAYERS]
    if unknown:
        print(f'未知图层: {unknown}, 可选: {list(LAYERS)}')
        sys.exit(1)

    for i, layer in enumerate(wanted):
        cfg = LAYERS[layer]
        print(f'[{i+1}/{len(wanted)}] 下载 {layer} ...', flush=True)
        result = fetch(cfg['query'])
        if result is None:
            print(f'  ✗ {layer} 下载失败(已重试), 跳过', flush=True)
            continue
        out_path = DATA_DIR / cfg['out']
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False)
        print(f'  ✓ {summarize(result)}', flush=True)
        print(f'    已保存 {out_path.name} ({out_path.stat().st_size // 1024}KB)', flush=True)
        if i < len(wanted) - 1:
            time.sleep(25)


if __name__ == '__main__':
    main()
