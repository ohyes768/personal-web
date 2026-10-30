"""Bounded collection of Xingfuli's public Hangzhou asking rents.

The same-neighborhood URL is anchored to a listing, not a neighborhood ID.
Never infer membership from that URL or from keyword-search recommendations.

Collection uses list API evidence: at most MAX_SAMPLES valid listings enter
statistics, and the crawl stops paging once that quota is met.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import re
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlencode, urlsplit

from src.services.fang_rentals import RentalCrawlCancelled, SeedRunResult
from src.services.xingfuli_transport import DEFAULT_XINGFULI_DELAY, XingfuliTransport
from src.services.rental_reference.statistics import XINGFULI_LIST_API_EVIDENCE, select_valid

BASE_URL = 'https://m.xflapp.com'

# 列表抽样：统计过滤后满 10 条有效整租即停，不再请求详情。
MAX_SAMPLES = 10


def _id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9]+', value):
        raise ValueError('幸福里 ID 必须为数字字符串')
    return value


def list_url(seed):
    return f'{BASE_URL}/zufang/neighbor-house-list/hz-{_id(seed)}.html'


def detail_url(lid):
    return f'{BASE_URL}/zufang/hz-{_id(lid)}.html'


def rental_list_api_url(seed, *, offset=0, search_id=None):
    params = dict(channel_id=94349583687, house_id=_id(seed), house_type=3,
                  aid=1370, app_name='f100', count=20, refresh_type=2,
                  offset=offset, list_style='same_neighborhood_list')
    if search_id:
        params['search_id'] = search_id
    return BASE_URL + '/f100/api/search_api/rent?' + urlencode(params)


def validate_url(url):
    p = urlsplit(url)
    if (p.scheme != 'https' or p.hostname != 'm.xflapp.com' or p.username or p.password
            or p.port not in {None, 443} or p.fragment
            or not (re.fullmatch(r'/zufang/(?:neighbor-house-list/)?hz-[0-9]+\.html', p.path)
                    or p.path == '/f100/api/search_api/rent')):
        raise ValueError('仅支持幸福里杭州公开租房列表、详情和分页接口')
    if p.path.endswith('.html') and p.query:
        raise ValueError('幸福里房源链接不能包含查询参数')
    return url


class _Scripts(HTMLParser):
    def __init__(self):
        super().__init__()
        self.selected = False
        self.buffer = ''
        self.payloads = []

    def handle_starttag(self, tag, attrs):
        if tag == 'script':
            self.selected = dict(attrs).get('name') == 'pia-ssr-data'
            self.buffer = ''

    def handle_data(self, data):
        if self.selected:
            self.buffer += data

    def handle_endtag(self, tag):
        if tag == 'script' and self.selected:
            self.payloads.append(json.loads(self.buffer))
            self.selected = False


def _page(body, expected_id):
    parser = _Scripts()
    parser.feed(body)
    if len(parser.payloads) != 1:
        raise ValueError('幸福里页面无法识别，可能要求验证或页面结构已变化')
    payload = parser.payloads[0]
    query = payload.get('query', {})
    if query.get('city') != 'hz' or query.get('id') != expected_id:
        raise ValueError('幸福里页面城市或房源 ID 与请求不一致')
    data = payload.get('data')
    if not isinstance(data, dict) or data.get('status') != 1:
        raise ValueError('幸福里页面未返回有效房源数据')
    return data


def _positive(value):
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (ValueError, TypeError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def _sample(row, sid, community_name, captured):
    if row.get('neighborhood_id') != sid:
        raise ValueError('幸福里列表混入其他小区，拒绝发布')
    lid = _id(row.get('id'))
    if row.get('rent_price_unit') != '元/月':
        raise ValueError('幸福里租金单位不受支持')
    title = str(row.get('title') or '')
    area = re.search(r'(-?\d+(?:\.\d+)?)㎡', str(row.get('sub_title') or ''))
    layout = re.search(r'\d+室(?:\d+厅)?(?:\d+卫)?', title)
    mode = {1: 'whole', 2: 'shared'}.get(row.get('rental_type'), 'unknown')
    flags = ['shared_rental'] if mode == 'shared' else ['unknown_rental_mode'] if mode == 'unknown' else []
    if re.search(r'独立厨卫|隔断|分割|单间|主卧|次卧', title):
        flags.append('suspected_partition')
    return dict(source='xingfuli', source_listing_id=lid, source_url=detail_url(lid),
                source_community_id=sid, community_name=community_name, title=title,
                monthly_rent_yuan=_positive(row.get('rent_price')), area_m2=_positive(area[1]) if area else None,
                layout=layout[0] if layout else None, rental_mode=mode, quality_flags=flags,
                detail_fetched=False, property_type=None, address=None, floor=None,
                captured_at=captured, published_at=None, price_kind='listing_rent')


def parse_listing(body, listing_id):
    """Parsed payload of a listing or same-neighborhood page."""
    return _page(body, listing_id)


def listing_neighborhood(body, listing_id):
    """Neighborhood that owns the listing page, or None when unknown."""
    cards = _page(body, listing_id)['info']['card_info']
    target = parse_qs(urlsplit(cards['neighborhood']['open_url']).query).get('neighborhood_id')
    return target[0] if target else None


def _detail_cards(body, listing_id, sid):
    cards = _page(body, listing_id)['info']['card_info']
    target = parse_qs(urlsplit(cards['neighborhood']['open_url']).query).get('neighborhood_id')
    if target != [sid]:
        raise ValueError('幸福里详情所属小区与关联不一致')
    return cards


def _enrich(sample, body, sid, property_type):
    cards = _detail_cards(body, sample['source_listing_id'], sid)
    core = cards['core_data']
    main = core['main_info']
    if main.get('price_unit') != '元/月':
        raise ValueError('幸福里详情租金单位不受支持')
    fields = {r['attr']: r.get('value') for r in core['core_info']}
    area = re.fullmatch(r'(\d+(?:\.\d+)?)㎡', fields.get('面积') or '')
    if not area or not _positive(main.get('price')):
        raise ValueError('幸福里详情缺少有效面积或月租')
    if not str(main.get('name') or '').startswith('整租·'):
        raise ValueError('幸福里详情出租方式与整租列表不一致')
    sample.update(monthly_rent_yuan=_positive(main['price']), area_m2=float(area[1]),
                  layout=fields.get('户型'), floor=fields.get('楼层'), detail_fetched=True,
                  property_type=property_type, property_type_origin='community_directory')


class XingfuliClient(XingfuliTransport):
    def __init__(self, timeout=20, *, directory=None, fetcher=None, delay=DEFAULT_XINGFULI_DELAY, cancel_event=None):
        super().__init__(timeout, directory=directory, fetcher=fetcher, delay=delay,
                         cancel_event=cancel_event, validate=validate_url)

    def crawl(self, source_id, seed_listing_id, *, community_name, property_type,
              max_pages=10, details=True, cancel_event=None):
        if cancel_event is not None:
            self.cancel = cancel_event
        _id(source_id)
        seed = list_url(seed_listing_id)
        result = SeedRunResult(seed=seed)
        starting_requests = self.request_count
        captured = dt.datetime.now(dt.UTC).isoformat()
        seen = set()
        offset = 0
        search_id = None
        try:
            for page in range(max_pages):
                self._check_cancel()
                response = json.loads(self.fetch(rental_list_api_url(
                    seed_listing_id, offset=offset, search_id=search_id)))
                if not isinstance(response, dict) or response.get('status') != 0 or not isinstance(response.get('data'), dict):
                    raise ValueError('幸福里列表 API 请求未成功')
                data = response['data']
                rows, more = data.get('items'), data.get('has_more')
                if not isinstance(rows, list) or not isinstance(more, bool):
                    raise ValueError('幸福里列表结构不完整')
                result.pages_fetched += 1
                added = 0
                quota_met = False
                for raw in rows:
                    sample = _sample(raw, source_id, community_name, captured)
                    if sample['source_listing_id'] in seen:
                        result.duplicate_ids += 1
                        continue
                    seen.add(sample['source_listing_id'])
                    added += 1
                    sample.update(verification_method=XINGFULI_LIST_API_EVIDENCE,
                                  property_type=property_type, property_type_origin='community_directory')
                    if quota_met:
                        sample['quality_flags'].append('outside_sampling_quota')
                    result.samples.append(sample)
                    quota_met = len(select_valid(result.samples)[0]) >= MAX_SAMPLES
                if quota_met:
                    result.status = 'complete'
                    break
                if not more:
                    if not result.samples:
                        raise ValueError('幸福里空列表缺少小区归属证据，保留原数据')
                    if rows and not added and page > 0:
                        raise ValueError('幸福里末页重复，拒绝发布不完整结果')
                    result.status = 'complete'
                    break
                next_offset, search = data.get('offset'), data.get('search_id')
                if (not added or not isinstance(next_offset, int) or isinstance(next_offset, bool)
                        or next_offset <= offset or not isinstance(search, str) or not search):
                    raise ValueError('幸福里分页未推进，拒绝发布不完整结果')
                if page + 1 == max_pages:
                    result.status = 'truncated'
                    result.pages_truncated = True
                    break
                offset, search_id = next_offset, search
            else:
                result.status = 'truncated'
                result.pages_truncated = True
        except RentalCrawlCancelled:
            raise
        except Exception as exc:
            result.status = 'list_failed'
            result.deferred = bool(self.cooldown_until and self.request_count == starting_requests)
            result.errors.append(dict(stage='list', url=seed, error=str(exc)))
        return result

    def close(self):
        pass
