"""查询时关联小区并按房源统计；不修改原始拍卖或普通房价。"""
import calendar
import json
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from statistics import median
from zoneinfo import ZoneInfo

from src.services.auction_fetcher import positive_number, community_name_index
from src.services.auction_store import AUCTION_PATH, read_store
from src.services.data_loader import DATA_DIR, load_communities

MAPPING_PATH = DATA_DIR / 'auction_community_mappings.json'
SHANGHAI = ZoneInfo('Asia/Shanghai')


def months_before(value, months):
    index = value.year * 12 + value.month - 1 - months
    year, month = divmod(index, 12)
    month += 1
    return value.replace(year=year, month=month, day=min(value.day, calendar.monthrange(year, month)[1]))


def parse_date(value):
    try:
        parsed = datetime.fromisoformat(str(value))
        return parsed.replace(tzinfo=SHANGHAI) if parsed.tzinfo is None else parsed.astimezone(SHANGHAI)
    except (ValueError, TypeError):
        return None


def load_mappings(path, communities):
    from src.services.community_registry import existing_registry
    registry = existing_registry(path.parent)
    if registry:
        from src.services.community_address import effective_address
        sources = registry.sources()
        valid_ids = {c['community_id'] for c in registry.communities() if effective_address(c.get('address'),
                     [r for r in sources if r['community_id'] == c['community_id'] and r['status'] == 'matched'])}
        from src.services.directory_workflow import is_enabled, admitted
        if is_enabled(registry):
            valid_ids = {c['community_id'] for c in admitted(registry, path.parent)}
        return {(r['source'], r['source_kind'] + '_id', r['source_id']): r['community_id']
                for r in sources if r['source'] == 'laipai' and r['status'] == 'matched' and r['community_id'] in valid_ids}
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(payload, dict) or payload.get('version') != 1 or not isinstance(payload.get('mappings'), list):
        raise ValueError('invalid auction mapping file')
    valid = {str(c['community_id']) for c in communities}
    result = {}
    for entry in payload['mappings']:
        if not isinstance(entry, dict):
            raise ValueError('invalid auction mapping entry')
        fields = [key for key in ('asset_id', 'auction_id') if entry.get(key)]
        if len(fields) != 1 or not isinstance(entry.get('source'), str) or not entry['source']:
            raise ValueError('mapping requires source and exactly one identity')
        key = (entry['source'], fields[0], str(entry[fields[0]]))
        cid = str(entry.get('community_id'))
        if cid not in valid or key in result:
            raise ValueError('unknown community or duplicate auction mapping')
        result[key] = cid
    return result


def associate_records(rows, communities, mappings, *, keep_unmatched=False):
    from src.services.community_registry import existing_registry
    registry = existing_registry(MAPPING_PATH.parent)
    names = community_name_index(communities)
    associated = []
    for row in rows:
        source = row['source']
        if registry:
            identities = [('asset', str(row.get('asset_id'))), ('auction', str(row['auction_id']))]
            if any(registry.is_ignored(source, kind, sid) for kind, sid in identities):
                continue
        cid = mappings.get((source, 'asset_id', str(row.get('asset_id'))))
        cid = cid or mappings.get((source, 'auction_id', str(row['auction_id'])))
        if not cid and not registry:
            matches = names.get(row.get('community_name'), set())
            if len(matches) == 1:
                cid = next(iter(matches))
            else:
                from src.services.auction_fetcher import fuzzy_community_match
                cid = (fuzzy_community_match(row.get('community_name') or '', communities) or {}).get('community_id')
        if cid or keep_unmatched:
            associated.append({**row, 'community_id': cid})
    return associated


def property_key(row):
    return (row['source'], 'asset' if row.get('asset_id') else 'auction',
            str(row.get('asset_id') or row['auction_id']))


def completed_properties(rows, now):
    groups = defaultdict(list)
    for row in rows:
        groups[property_key(row)].append(row)
    result = []
    for rounds in groups.values():
        sales = [(parse_date(r.get('end_at')), r) for r in rounds
                 if r.get('status') == 'done' and positive_number(r.get('deal_price_yuan'))]
        sales = [(date, r) for date, r in sales if date and date <= now]
        if not sales:
            continue
        date, latest = max(sales, key=lambda pair: (pair[0], str(pair[1]['auction_id'])))
        area = positive_number(latest.get('area_m2'))
        record = {**latest, 'end_at': date.isoformat(), 'area_m2': area,
                  'deal_unit_price': rounded(latest['deal_price_yuan'] / area) if area else None,
                  'identity_warning': None if latest.get('asset_id') else '缺房源身份，无法识别跨轮次重复',
                  'rounds': sorted(rounds, key=lambda r: (parse_date(r.get('end_at')) or datetime.min.replace(tzinfo=SHANGHAI), str(r['auction_id'])), reverse=True)}
        result.append(record)
    return sorted(result, key=lambda r: (r['end_at'], str(r['auction_id'])), reverse=True)


def rounded(value):
    return int(Decimal(str(value)).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def build_history(rows, communities, mappings, community_id, *, now=None, period='12m', area_band='all', page=1, page_size=20):
    now = (now or datetime.now(SHANGHAI)).astimezone(SHANGHAI)
    if community_id not in {str(c['community_id']) for c in communities}:
        raise KeyError(community_id)
    if period not in {'12m', '24m', 'all'} or area_band not in {'all', 'lt90', '90to144', 'gte144'}:
        raise ValueError('invalid history filters')
    associated = associate_records(rows, communities, mappings)
    records = [r for r in completed_properties(associated, now) if r['community_id'] == community_id]
    cutoff = months_before(now, int(period[:-1])) if period != 'all' else None
    filtered = []
    for record in records:
        area = record['area_m2']
        if cutoff and parse_date(record['end_at']) < cutoff:
            continue
        if area_band != 'all' and (not area or not {'lt90': area < 90, '90to144': 90 <= area < 144, 'gte144': area >= 144}[area_band]):
            continue
        filtered.append(record)
    prices = [r['deal_price_yuan'] / r['area_m2'] for r in filtered if r['area_m2']]
    stats = {'deal_property_count': len(filtered), 'unit_price_sample_count': len(prices),
             'median_unit_price_yuan': rounded(median(prices)) if prices else None,
             'min_unit_price_yuan': rounded(min(prices)) if prices else None,
             'max_unit_price_yuan': rounded(max(prices)) if prices else None,
             'latest_end_at': filtered[0]['end_at'] if filtered else None,
             'sample_warning': '参考样本较少' if len(prices) < 3 else None}
    start = (page - 1) * page_size
    return {'community_id': community_id, 'as_of': now.isoformat(), 'period': period, 'area_band': area_band,
            'stats': stats, 'records': filtered[start:start + page_size], 'total': len(filtered),
            'page': page, 'page_size': page_size}


def load_context():
    communities = load_communities()
    if not communities:
        raise ValueError('community data unavailable')
    store = read_store(AUCTION_PATH)
    mappings = load_mappings(MAPPING_PATH, communities)
    metadata = {'available': AUCTION_PATH.exists(), 'last_run': store.get('last_run'), 'source': 'laipai'}
    return store['records'], communities, mappings, metadata


def get_history(community_id, **filters):
    rows, communities, mappings, metadata = load_context()
    return {**build_history(rows, communities, mappings, community_id, **filters), **metadata}


def get_summary():
    rows, communities, mappings, metadata = load_context()
    records = completed_properties(associate_records(rows, communities, mappings), datetime.now(SHANGHAI))
    counts = defaultdict(int)
    for row in records:
        counts[row['community_id']] += 1
    return {'counts': dict(counts), **metadata}
