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

    def search_name(self, name, district, types='120300|120203'):
        """Search POIs by name. `types=None` searches every category (use review);
        the default keeps the residential whitelist so position lookups stay narrow."""
        params = {'key': self.key, 'keywords': name, 'city': '杭州', 'citylimit': 'true',
                  'offset': 25, 'page': 1, 'extensions': 'base'}
        if types is not None:
            params['types'] = types
        try:
            response = self.session.get('https://restapi.amap.com/v3/place/text', params=params, timeout=20)
            response.raise_for_status()
            data = response.json()
        except Exception:
            raise ValueError('高德位置补全请求失败') from None
        if data.get('status') != '1' or not isinstance(data.get('pois'), list) or not str(data.get('count', '')).isdigit():
            raise ValueError('高德位置补全返回异常')
        return data['pois'], int(data['count'])

    def close(self):
        self.session.close()


# 出入口、停车场等附属设施不是小区本身，定位与用途复核都排除。
_ATTACHED_PLACE = re.compile(r'(?:出入口|停车场|地下车库|物业服务中心|售楼处|[东西南北](?:门|出入口)|\d+\s*(?:幢|栋|号楼))$')


def normalize_poi(poi, *, district='滨江'):
    sid, name = poi.get('id'), poi.get('name')
    if not isinstance(sid, str) or not sid or not isinstance(name, str) or not name.strip():
        return None
    # 120203 商住两用楼宇: TMSF 住宅项目（公馆/公寓）在高德常落在商住楼宇分类下。
    # 高德可能返回复合分类码（如 "120302|120203"），任一段命中白名单即接受。
    typecodes = set(str(poi.get('typecode') or '').split('|'))
    if district not in {'滨江', '萧山'} or poi.get('adname') != district + '区' or not typecodes & {'120300', '120301', '120302', '120303', '120304', '120203'}:
        return None
    # Keep phase/directional names. Exclude subordinate entrances, buildings and facilities.
    if _ATTACHED_PLACE.search(name):
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


def normalize_poi_category(poi, *, district='滨江'):
    """Unfiltered Amap POI: any category, kept for use-category review.

    Unlike `normalize_poi` it accepts non-residential categories and does not
    require coordinates — a review judges the recorded use, not the map point.
    """
    sid, name = poi.get('id'), poi.get('name')
    if not isinstance(sid, str) or not sid or not isinstance(name, str) or not name.strip():
        return None
    if poi.get('adname') != district + '区' or _ATTACHED_PLACE.search(name):
        return None
    longitude = latitude = None
    try:
        longitude, latitude = map(float, str(poi.get('location', '')).split(','))
    except (ValueError, TypeError):
        longitude = latitude = None
    else:
        if not all(math.isfinite(v) for v in (longitude, latitude)):
            longitude = latitude = None
    return dict(source='amap', source_kind='poi', source_id=sid, name=name.strip(), district=district,
                address=poi.get('address') if isinstance(poi.get('address'), str) else '',
                longitude=longitude, latitude=latitude, coordinate_system='gcj02',
                poi_type=poi.get('type') if isinstance(poi.get('type'), str) else '',
                poi_typecode=str(poi.get('typecode') or ''), captured_at=now(),
                source_url='https://www.amap.com/search?query=' + quote(name))
