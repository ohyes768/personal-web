"""Bounded spatial discovery of residential POIs; map labels are not property use."""
import math
import os
import re
from urllib.parse import quote

from src.core.boundary import BINJIANG_BOUNDARY, is_in_binjiang
from src.services.community_registry import now


class AmapIncomplete(ValueError):
    pass


def web_service_key():
    key = os.getenv('AMAP_WEB_SERVICE_KEY') or os.getenv('GAODE_API_KEY')
    if not key:
        try:
            from scripts._gaode_config import GAODE_API_KEY
            key = GAODE_API_KEY
        except ImportError:
            pass
    if not key:
        raise ValueError('未配置高德 Web 服务 Key（AMAP_WEB_SERVICE_KEY 或 GAODE_API_KEY）')
    return key


class AmapClient:
    def __init__(self):
        from curl_cffi.requests import Session
        self.key = web_service_key()
        self.session = Session()

    def search(self, box, page):
        west, south, east, north = box
        try:
            response = self.session.get('https://restapi.amap.com/v3/place/polygon', params={
                'key': self.key, 'polygon': f'{west:.6f},{north:.6f}|{east:.6f},{south:.6f}',
                'types': '120300', 'offset': 25, 'page': page, 'extensions': 'base'}, timeout=20)
            response.raise_for_status()
            data = response.json()
        except Exception:
            # Transport exceptions often contain the request URL and secret key.
            raise ValueError('高德请求失败，请稍后重试') from None
        if data.get('status') != '1':
            code = str(data.get('infocode', ''))
            code = code if code.isdigit() else 'unknown'
            raise ValueError(f'高德查询失败（错误码 {code}），请检查服务端 Key、权限和配额')
        if not isinstance(data.get('pois'), list) or not str(data.get('count', '')).isdigit():
            raise ValueError('高德返回数据格式异常')
        return data['pois'], int(data['count'])

    def close(self):
        self.session.close()


def normalize_poi(poi):
    sid, name = poi.get('id'), poi.get('name')
    if not isinstance(sid, str) or not sid or not isinstance(name, str) or not name.strip():
        return None
    if poi.get('adname') != '滨江区' or str(poi.get('typecode')) not in {'120300', '120301', '120302', '120303', '120304'}:
        return None
    # Keep phase/directional names. Exclude subordinate entrances, buildings and facilities.
    if re.search(r'(?:出入口|停车场|地下车库|物业服务中心|售楼处|[东西南北](?:门|出入口)|\d+\s*(?:幢|栋|号楼))$', name):
        return None
    try:
        lng, lat = map(float, str(poi.get('location', '')).split(','))
    except (ValueError, TypeError):
        raise ValueError('高德住宅地点缺少有效坐标') from None
    if not all(math.isfinite(v) for v in (lng, lat)):
        raise ValueError('高德住宅地点坐标无效')
    if not is_in_binjiang(lng, lat):
        return None
    return dict(source='amap', source_kind='poi', source_id=sid, name=name.strip(), district='滨江',
                address=poi.get('address') if isinstance(poi.get('address'), str) else '',
                longitude=lng, latitude=lat, coordinate_system='gcj02',
                poi_type=poi.get('type') if isinstance(poi.get('type'), str) else '',
                poi_typecode=str(poi['typecode']), residential_hint=True, captured_at=now(),
                source_url='https://www.amap.com/search?query=' + quote(name))


def discover(cancel, ignored, *, client=None, max_requests=256, max_depth=8):
    client = client or AmapClient()
    seen = set()
    requests = 0
    filtered = 0
    duplicates = 0
    cells = 0
    points = BINJIANG_BOUNDARY
    root = (min(p[0] for p in points), min(p[1] for p in points),
            max(p[0] for p in points), max(p[1] for p in points))
    stack = [(root, 0)]
    incomplete_cells = 0
    incomplete_reasons = {}

    def coverage(complete=False):
        return {'_coverage': dict(requests=requests, cells=cells, unique=len(seen),
                                  filtered=filtered, duplicates=duplicates,
                                  complete=complete, incomplete_cells=incomplete_cells,
                                  scope='滨江住宅区 POI')}

    def subdivide(box, depth, reason):
        nonlocal incomplete_cells
        if depth >= max_depth:
            incomplete_cells += 1
            incomplete_reasons[reason] = incomplete_reasons.get(reason, 0) + 1
            return
        west, south, east, north = box
        midx, midy = (west + east) / 2, (south + north) / 2
        stack.extend((cell, depth + 1) for cell in (
            (west, south, midx, midy), (midx, south, east, midy),
            (west, midy, midx, north), (midx, midy, east, north)))

    try:
        while stack:
            box, depth = stack.pop()
            cells += 1
            page_ids = set()
            cell_ids = set()
            reported_count = 0
            for page in range(1, 9):
                if cancel.is_set() or (requests and cancel.wait(2)):
                    raise InterruptedError('采集已取消')
                if requests >= max_requests:
                    raise AmapIncomplete('高德达到本轮请求预算，部分区域尚未查完')
                requests += 1
                pois, count = client.search(box, page)
                reported_count = max(reported_count, count)
                ids = tuple(sorted(str(p.get('id')) for p in pois))
                abnormal = None
                if ids and ids in page_ids:
                    abnormal = '分页重复'
                elif not pois and len(cell_ids) < reported_count:
                    abnormal = '列表提前结束'
                if abnormal:
                    subdivide(box, depth, abnormal)
                    yield coverage()
                    break
                page_ids.add(ids)
                for poi in pois:
                    if cancel.is_set():
                        raise InterruptedError('采集已取消')
                    # Count all raw identities in this cell, including filtered
                    # and globally seen records, but never overlapping rows twice.
                    sid = poi.get('id')
                    if isinstance(sid, str) and sid:
                        cell_ids.add(sid)
                    row = normalize_poi(poi)
                    if row is None:
                        filtered += 1
                        continue
                    if row['source_id'] in seen:
                        duplicates += 1
                        continue
                    seen.add(row['source_id'])
                    yield row  # Ignored identities are counted by the common collector; no details requested.
                # A saturated result may be capped by the upstream search service.
                finished = False
                if reported_count >= 200 and depth < max_depth:
                    subdivide(box, depth, '搜索上限')
                    finished = True
                elif len(cell_ids) >= reported_count:
                    # A terminal saturated cell can still expose later pages.
                    # Exhaust those first, but do not mistake the capped count
                    # for proof that this cell has no additional results.
                    if reported_count >= 200:
                        subdivide(box, depth, '搜索上限')
                    finished = True
                elif page == 8:
                    # Short pages can exhaust eight pages below the saturation
                    # threshold. Recover via smaller boxes, or mark the leaf.
                    subdivide(box, depth, '分页上限')
                    finished = True
                yield coverage()
                if finished:
                    break
        yield coverage(complete=not incomplete_cells)
        if incomplete_cells:
            reasons = '、'.join(f'{reason} {number} 个' for reason, number in incomplete_reasons.items())
            raise AmapIncomplete(f'高德有 {incomplete_cells} 个区域切分到深度上限仍未查完（{reasons}），'
                                 '其他区域已继续查询；住宅目录覆盖不完整')
    finally:
        client.close()
