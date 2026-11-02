"""Known-community position lookup and legacy POI validation; no regional discovery."""
import math
import os
import re
import threading
import time
from urllib.parse import quote

from src.core.boundary import is_in_binjiang, is_in_xiaoshan_border
from src.services.community_registry import now


# One worker serves the backend. Share the gate across clients and tasks, not
# just communities: pagination and alias lookups also consume upstream QPS.
_REQUEST_LOCK = threading.Lock()
_NEXT_REQUEST_AT = 0.0
_REQUEST_INTERVAL = 2.0
_RETRY_DELAYS = (2.0, 4.0, 8.0)
_QPS_CODES = {'10014', '10015', '10019', '10020', '10021', '10029'}


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

    def search_name(self, name, district, types='120300|120203', *, page=1, before_request=None):
        """Search POIs by name. `types=None` searches every category (use review);
        the default keeps the residential whitelist so position lookups stay narrow.
        Use district adcodes to restrict upstream results before the 25-result limit."""
        city = {'滨江': '330108', '萧山': '330109'}.get(district, '杭州')
        params = {'key': self.key, 'keywords': name, 'city': city, 'citylimit': 'true',
                  'offset': 25, 'page': page, 'extensions': 'base'}
        if types is not None:
            params['types'] = types
        global _NEXT_REQUEST_AT
        for attempt in range(len(_RETRY_DELAYS) + 1):
            # Serialize the actual HTTP call too, so slow requests cannot let
            # another client overtake its reservation and produce a burst.
            with _REQUEST_LOCK:
                wait = _NEXT_REQUEST_AT - time.monotonic()
                if wait > 0:
                    time.sleep(wait)
                if before_request:
                    # Keep cancellation and explicit HTTP budgets effective on
                    # every retry, not just the first attempt of a page.
                    before_request()
                try:
                    response = self.session.get('https://restapi.amap.com/v3/place/text', params=params, timeout=20)
                    limited = getattr(response, 'status_code', None) == 429
                    if limited:
                        code = 'HTTP 429'
                    else:
                        response.raise_for_status()
                        data = response.json()
                        if not isinstance(data, dict):
                            raise ValueError()
                        raw_code = str(data.get('infocode', ''))
                        code = raw_code if re.fullmatch(r'\d{5}', raw_code) else '未知'
                        limited = data.get('status') != '1' and code in _QPS_CODES
                except Exception:
                    raise ValueError('高德位置补全请求失败') from None
                finally:
                    _NEXT_REQUEST_AT = time.monotonic() + _REQUEST_INTERVAL
                if limited:
                    # Cooldown is shared: other tasks must respect it as well.
                    _NEXT_REQUEST_AT = time.monotonic() + _RETRY_DELAYS[min(attempt, len(_RETRY_DELAYS) - 1)]
            if limited:
                if attempt == len(_RETRY_DELAYS):
                    raise ValueError(f'高德查询频率超限（{code}），退避重试后仍失败，请稍后继续')
                continue
            if data.get('status') != '1':
                raise ValueError(f'高德位置补全返回异常（错误码 {code}）')
            if not isinstance(data.get('pois'), list) or not str(data.get('count', '')).isdigit():
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
