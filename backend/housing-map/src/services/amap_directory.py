"""Known-community position lookup and legacy POI validation; no regional discovery."""
import math
import os
import re
from urllib.parse import quote

from src.core.boundary import is_in_binjiang, is_in_xiaoshan_border
from src.services.community_registry import now


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

    def search_name(self, name, district):
        try:
            response = self.session.get('https://restapi.amap.com/v3/place/text', params={
                'key': self.key, 'keywords': name, 'city': '杭州', 'citylimit': 'true',
                'types': '120300', 'offset': 25, 'page': 1, 'extensions': 'base'}, timeout=20)
            response.raise_for_status()
            data = response.json()
        except Exception:
            raise ValueError('高德位置补全请求失败') from None
        if data.get('status') != '1' or not isinstance(data.get('pois'), list) or not str(data.get('count', '')).isdigit():
            raise ValueError('高德位置补全返回异常')
        return data['pois'], int(data['count'])

    def close(self):
        self.session.close()


def normalize_poi(poi, *, district='滨江'):
    sid, name = poi.get('id'), poi.get('name')
    if not isinstance(sid, str) or not sid or not isinstance(name, str) or not name.strip():
        return None
    if district not in {'滨江', '萧山'} or poi.get('adname') != district + '区' or str(poi.get('typecode')) not in {'120300', '120301', '120302', '120303', '120304'}:
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
    if not (is_in_binjiang(lng, lat) if district == '滨江' else is_in_xiaoshan_border(lng, lat)):
        return None
    return dict(source='amap', source_kind='poi', source_id=sid, name=name.strip(), district=district,
                address=poi.get('address') if isinstance(poi.get('address'), str) else '',
                longitude=lng, latitude=lat, coordinate_system='gcj02',
                poi_type=poi.get('type') if isinstance(poi.get('type'), str) else '',
                poi_typecode=str(poi['typecode']), residential_hint=True, captured_at=now(),
                source_url='https://www.amap.com/search?query=' + quote(name))
