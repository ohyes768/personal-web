"""Discover the Xingfuli rental source of an admitted community.

A keyword search on the platform answers with HTTP 200 and unrelated listings
even when the name matches nothing, so a search response never proves identity.
The search only nominates which community homepage to read; identity, address,
position and the actual rental entry all come from the homepage and the
listing pages it links to.
"""
from __future__ import annotations

import json
import re
from urllib.parse import parse_qsl, urlencode, urlsplit

from src.services.xingfuli_rentals import detail_url, listing_neighborhood, list_url
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
# Channel order used by the bounded discovery: the cheapest channel that can
# name a whole community comes first.
CHANNEL_ORDER = ('second_hand', 'rent', 'neighborhood')

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


def homepage_url(neighborhood_id):
    if not re.fullmatch(r'[0-9]+', str(neighborhood_id or '')):
        raise ValueError('幸福里小区 ID 必须为数字字符串')
    return f'{BASE_URL}/xiaoqu/hz-{neighborhood_id}.html'


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


def name_conflict(internal_names, platform_name):
    """True when the platform names a sub-division or another place.

    白金海岸(南区) is a phase of 白金海岸, not the community itself; a human
    confirmation may not force such a binding.
    """
    platform = str(platform_name or '').strip()
    if not platform:
        return True
    qualifier = phase_of(platform)
    if qualifier:
        # The platform entity is a qualified variant; only an internal name that
        # carries the same qualifier can be the same place.
        return not any(qualifier in str(name or '') for name in internal_names if name)
    normalized_platform = platform.replace(' ', '').replace('　', '')
    for name in internal_names:
        if not name:
            continue
        normalized_internal = str(name).replace(' ', '').replace('　', '')
        if normalized_platform == normalized_internal:
            return False
    return False


class XingfuliDiscovery(XingfuliTransport):
    """Reads the platform's public search and community homepage pages."""

    def __init__(self, timeout=20, *, directory=None, fetcher=None, delay=5, cancel_event=None):
        super().__init__(timeout, directory=directory, fetcher=fetcher, delay=delay,
                         cancel_event=cancel_event, validate=validate_discovery_url)

    def search(self, name, channel):
        """Neighborhood identities the platform reported for a name on one channel."""
        if channel not in SEARCH_CHANNELS:
            raise ValueError('未知的幸福里搜索通道')
        house_type, channel_id, page_type = SEARCH_CHANNELS[channel]
        url = BASE_URL + '/f100/api/search?' + urlencode({
            'city_id': CITY_ID, 'house_type': house_type, 'channel_id': channel_id,
            'full_text': name, 'count': 20, 'offset': 0, 'page_type': page_type})
        payload = json.loads(self.fetch(url))
        if payload.get('status') != 0 or not isinstance(payload.get('data'), dict):
            raise ValueError('幸福里搜索未返回有效数据')
        items = payload['data'].get('items')
        return search_groups(items if isinstance(items, list) else [], channel)

    def homepage(self, neighborhood_id):
        return parse_homepage(self.fetch(homepage_url(neighborhood_id)), neighborhood_id)

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
