"""Discover the Xingfuli rental source of an admitted community.

A keyword search on the platform answers with HTTP 200 and unrelated listings
even when the name matches nothing, so a search response never proves identity.
The search only nominates community IDs. Identity comes from the community
info API; rental seeds are fetched separately after a candidate is selected.
A fresh rental list API response proves membership of the seed we actually bind.
"""
from __future__ import annotations

import json
import re
from urllib.parse import parse_qsl, urlencode, urlsplit

from src.services.xingfuli_transport import DEFAULT_XINGFULI_DELAY
from src.services.xingfuli_rentals import detail_url, listing_neighborhood, list_url, rental_list_api_url
from src.services.xingfuli_transport import XingfuliTransport

BASE_URL = 'https://m.xflapp.com'
CITY_ID = 1853

# house_type / channel_id / page_type of the platform's own search channels.
# The channels index differently: second-hand listings name the whole community,
# the neighborhood channel may only name a phase, rent listings anchor on a seed.
SEARCH_CHANNELS = {
    'second_hand': (2, 94349530167, 'house_list'),
    'rent': (3, 94349530177, 'rent_list'),
    'neighborhood': (4, 94349530172, 'neighborhood_list'),
}
SEARCH_PARAMS = frozenset({'city_id', 'house_type', 'channel_id', 'full_text', 'count', 'offset', 'page_type'})
SEARCH_PAGE_SIZE = 20
# Identity search only. Second-hand names the whole community; the neighborhood
# channel adds address and coordinates. Rent search is not an identity source:
# it misses communities, returns city-wide listings, and can split one community
# into phases. Rental listings are fetched later, after the neighborhood id is known.
CHANNEL_ORDER = ('second_hand', 'neighborhood')

QUALIFIER = re.compile(r'[（(]([^（()）]{1,10})[）)]')
RENT_TITLE = re.compile(r'^[整合]租[·.]\s*(.+?)\s*\d+室')


def validate_discovery_url(url):
    p = urlsplit(url)
    if (p.scheme != 'https' or p.hostname != 'm.xflapp.com' or p.username or p.password
            or p.port not in {None, 443} or p.fragment):
        raise ValueError('仅支持幸福里杭州公开页面')
    if p.path == '/f100/api/search':
        if not set(dict(parse_qsl(p.query))) <= SEARCH_PARAMS:
            raise ValueError('幸福里搜索参数不在允许范围')
        return url
    if p.path == '/f100/api/search_api/rent':
        pairs = parse_qsl(p.query, keep_blank_values=True)
        params = dict(pairs)
        expected = parse_qsl(urlsplit(rental_list_api_url(params.get('house_id', ''))).query)
        if sorted(pairs) != sorted(expected):
            raise ValueError('幸福里租房列表API参数不在允许范围')
        return url
    api_params = {
        '/f100/api/neighborhood/info': {'neighborhood_id'},
        '/f100/api/same_neighborhood_rent': {'neighborhood_id', 'city_id', 'offset', 'count'},
    }
    if p.path in api_params:
        pairs = parse_qsl(p.query, keep_blank_values=True)
        params = dict(pairs)
        if (set(params) != api_params[p.path] or len(params) != len(pairs)
                or not re.fullmatch(r'[0-9]+', params.get('neighborhood_id', ''))
                or (p.path.endswith('same_neighborhood_rent') and
                    (params['city_id'] != str(CITY_ID) or params['offset'] != '0' or params['count'] != '10'))):
            raise ValueError('幸福里小区API参数不在允许范围')
        return url
    if re.fullmatch(r'/xiaoqu/hz-[0-9]+\.html', p.path):
        if p.query:
            raise ValueError('幸福里小区主页不能包含查询参数')
        return url
    # Listing pages are the already verified paths of the rent collector; the
    # discovery adapter only reads them to prove who owns a seed.
    if re.fullmatch(r'/zufang/(?:neighbor-house-list/)?hz-[0-9]+\.html', p.path):
        if p.query:
            raise ValueError('幸福里房源链接不能包含查询参数')
        return url
    raise ValueError('仅支持幸福里杭州公开搜索、小区主页与房源页')


def _community_id(neighborhood_id):
    if not re.fullmatch(r'[0-9]+', str(neighborhood_id or '')):
        raise ValueError('幸福里小区 ID 必须为数字字符串')
    return str(neighborhood_id)


def homepage_url(neighborhood_id):
    return f'{BASE_URL}/xiaoqu/hz-{_community_id(neighborhood_id)}.html'


def _number(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and abs(number) != float('inf') else None


def phase_of(name):
    """Qualifier carried by the platform name, e.g. 白金海岸(南区) -> 南区."""
    match = QUALIFIER.search(str(name or ''))
    return match.group(1) if match else ''


def address_district(address):
    """Administrative district the platform address names, if any."""
    match = re.search(r'([一-龥]{2,4}区)', str(address or ''))
    return match.group(1) if match else ''


def parse_homepage(html, expected_id):
    """Identity and rental entry of a community homepage."""
    marker = 'window._SSR_DATA = '
    index = html.find(marker)
    if index < 0:
        raise ValueError('幸福里小区主页无法识别，可能要求验证或页面结构已变化')
    try:
        payload, _ = json.JSONDecoder().raw_decode(html[index + len(marker):])
    except ValueError:
        raise ValueError('幸福里小区主页数据无法解析') from None
    loaders = (payload.get('data') or {}).get('loadersData') or {}
    detail = None
    for value in loaders.values():
        data = value.get('data') if isinstance(value, dict) else None
        if isinstance(data, dict) and isinstance(data.get('neighborhood_info'), dict):
            detail = data
            break
    if detail is None:
        raise ValueError('幸福里小区主页缺少小区信息')
    info = detail['neighborhood_info']
    if str(info.get('id')) != str(expected_id):
        raise ValueError('幸福里小区主页身份与请求不一致')
    rent = detail.get('rentInNeighbor') or {}
    seeds = []
    for item in rent.get('items') or []:
        seed = str((item or {}).get('id') or '')
        if re.fullmatch(r'[0-9]+', seed) and seed not in seeds:
            seeds.append(seed)
    return {
        'neighborhood_id': str(expected_id),
        'name': str(info.get('name') or ''),
        'address': str(info.get('address') or ''),
        'longitude': _number(info.get('gaode_lng')),
        'latitude': _number(info.get('gaode_lat')),
        'coordinate_system': 'gcj02',
        'rent_total': rent.get('total'),
        'rent_has_more': bool(rent.get('has_more')),
        'seeds': seeds,
    }


def _api_data(body):
    try:
        payload = json.loads(body)
    except (ValueError, TypeError):
        raise ValueError('幸福里小区API未返回有效JSON') from None
    if (not isinstance(payload, dict) or type(payload.get('status')) is not int
            or payload['status'] != 0 or not isinstance(payload.get('data'), dict)):
        raise ValueError('幸福里小区API未返回有效数据')
    return payload['data']


def parse_community_info(body, expected_id):
    info = _api_data(body).get('neighborhood_info')
    if not isinstance(info, dict) or str(info.get('id')) != expected_id:
        raise ValueError('幸福里小区API身份与请求不一致')
    if str(info.get('city_id')) != str(CITY_ID):
        raise ValueError('幸福里小区API城市与杭州不一致')
    if (not isinstance(info.get('name'), str) or not info['name'].strip()
            or not isinstance(info.get('address'), str)
            or not isinstance(info.get('district_name', ''), str)):
        raise ValueError('幸福里小区API缺少有效名称或地址字段')
    coordinates = []
    for key, limit in (('gaode_lng', 180), ('gaode_lat', 90)):
        raw = info.get(key)
        value = _number(raw)
        if raw not in (None, '') and (isinstance(raw, bool) or value is None or abs(value) > limit):
            raise ValueError('幸福里小区API坐标无效')
        coordinates.append(value)
    return dict(neighborhood_id=expected_id, name=info['name'].strip(), address=info['address'],
                longitude=coordinates[0], latitude=coordinates[1], coordinate_system='gcj02',
                city_id=CITY_ID, district=info.get('district_name', ''))


def parse_rental_entry(body, expected_id):
    data = _api_data(body)
    items, total, more = data.get('items'), data.get('total'), data.get('has_more')
    if (not isinstance(items, list) or type(total) is not int or total < 0
            or not isinstance(more, bool) or total < len(items)
            or (not items and (total > 0 or more))):
        raise ValueError('幸福里租房入口API结构不完整')
    seeds = []
    for item in items:
        if (not isinstance(item, dict) or not isinstance(item.get('id'), str)
                or not re.fullmatch(r'[0-9]+', item['id'])):
            raise ValueError('幸福里租房入口API种子无效')
        # The current API omits membership. If supplied, never ignore a conflict.
        if item.get('neighborhood_id') is not None and str(item['neighborhood_id']) != expected_id:
            raise ValueError('幸福里租房入口API混入其他小区')
        if item['id'] not in seeds:
            seeds.append(item['id'])
    return dict(neighborhood_id=expected_id, seeds=seeds, rent_total=total, rent_has_more=more)


def search_groups(items, channel='rent'):
    """Community identities the platform reported, keyed by neighborhood id.

    The rent channel also anchors each item on a listing seed; the other
    channels report sale or community cards whose id is not a rent seed.
    """
    groups = {}
    for item in items or []:
        if not isinstance(item, dict):
            continue
        info = item.get('neighborhood_info') or {}
        neighborhood_id = str(info.get('id') or item.get('neighborhood_id') or '')
        if not re.fullmatch(r'[0-9]+', neighborhood_id):
            continue
        name = str(info.get('name') or '').strip()
        if not name:
            for field in item.get('core_info') or []:
                if isinstance(field, dict) and field.get('attr') == '小区名':
                    name = str(field.get('value') or '').strip()
                    break
        if not name:
            match = RENT_TITLE.match(str(item.get('title') or ''))
            name = match.group(1).strip() if match else ''
        if not name:
            continue
        group = groups.setdefault(neighborhood_id, {'name': name, 'seeds': []})
        if channel == 'rent':
            seed = str(item.get('id') or '')
            if re.fullmatch(r'[0-9]+', seed) and seed not in group['seeds']:
                group['seeds'].append(seed)
    return groups


class XingfuliDiscovery(XingfuliTransport):
    """Reads public search/info/entry APIs and verifies seeds against listings."""

    def __init__(self, timeout=20, *, directory=None, fetcher=None, delay=DEFAULT_XINGFULI_DELAY, cancel_event=None):
        super().__init__(timeout, directory=directory, fetcher=fetcher, delay=delay,
                         cancel_event=cancel_event, validate=validate_discovery_url)

    def search(self, name, channel, offset=0):
        """Neighborhood identities the platform reported for a name on one channel."""
        if channel not in SEARCH_CHANNELS:
            raise ValueError('未知的幸福里搜索通道')
        house_type, channel_id, page_type = SEARCH_CHANNELS[channel]
        url = BASE_URL + '/f100/api/search?' + urlencode({
            'city_id': CITY_ID, 'house_type': house_type, 'channel_id': channel_id,
            'full_text': name, 'count': SEARCH_PAGE_SIZE, 'offset': offset, 'page_type': page_type})
        payload = json.loads(self.fetch(url))
        if payload.get('status') != 0 or not isinstance(payload.get('data'), dict):
            raise ValueError('幸福里搜索未返回有效数据')
        items = payload['data'].get('items')
        if not isinstance(items, list):
            raise ValueError('幸福里搜索结果不完整')
        total = payload['data'].get('total')
        # A filled page can omit another plausible identity. It cannot
        # authorize automatic binding, even when one visible result is strong.
        self.search_complete = len(items) < SEARCH_PAGE_SIZE and not (
            isinstance(total, (int, float)) and total > len(items))
        return search_groups(items, channel)

    def community_info(self, neighborhood_id):
        neighborhood_id = _community_id(neighborhood_id)
        url = BASE_URL + '/f100/api/neighborhood/info?' + urlencode({'neighborhood_id': neighborhood_id})
        return parse_community_info(self.fetch(url), neighborhood_id)

    def rental_entry(self, neighborhood_id):
        neighborhood_id = _community_id(neighborhood_id)
        url = BASE_URL + '/f100/api/same_neighborhood_rent?' + urlencode({
            'neighborhood_id': neighborhood_id, 'city_id': CITY_ID, 'offset': 0, 'count': 10})
        return parse_rental_entry(self.fetch(url), neighborhood_id)

    def verified_rental_seed(self, seed, neighborhood_id):
        """Return a live, explicitly owned listing; the old anchor may be absent."""
        neighborhood_id = _community_id(neighborhood_id)
        data = _api_data(self.fetch(rental_list_api_url(seed)))
        rows = data.get('items')
        if not isinstance(rows, list) or not isinstance(data.get('has_more'), bool):
            raise ValueError('幸福里租房列表API结构不完整')
        if not rows:
            return None
        for row in rows:
            if (not isinstance(row, dict) or not isinstance(row.get('id'), str)
                    or not re.fullmatch(r'[0-9]+', row['id'])
                    or row.get('neighborhood_id') != neighborhood_id):
                raise ValueError('幸福里租房列表归属不一致或身份缺失')
        # Bind a listing from verified rows, never the unverified entry anchor.
        return rows[0]['id']

    def listing_owner(self, seed):
        """Neighborhood that actually owns the listing behind a seed."""
        return listing_neighborhood(self.fetch(detail_url(seed)), seed)

    def listing_owner_from_list(self, seed, neighborhood_id):
        """Confirm the seed's same-neighborhood list belongs to the community."""
        from src.services.xingfuli_rentals import parse_listing
        data = parse_listing(self.fetch(list_url(seed)), seed)
        rows = data.get('_list')
        if not isinstance(rows, list) or not rows:
            return False
        return all(str(row.get('neighborhood_id')) == str(neighborhood_id) for row in rows)
