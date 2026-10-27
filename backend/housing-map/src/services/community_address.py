"""Address evidence for residential admission; coordinates alone are insufficient."""
import re

POLICY_KEY = 'admission_address_policy'
POLICY_RULE = 'amap-subject-address-v1'

MISSING_ADDRESSES = {'', '暂无', '未知', '暂无地址', '地址暂无', '未知地址', '地址未知', '无',
                     '-', '--', '—', '–', 'null', 'none', 'n/a', '未提供'}


def valid_address(value):
    return isinstance(value, str) and re.sub(r'\s+', '', value).casefold() not in MISSING_ADDRESSES


def effective_address(address, members=()):
    if valid_address(address):
        return address.strip()
    return next((r['address'].strip() for r in members if valid_address(r.get('address'))), '')


def admission_address(community, records=()):
    """Read-only evidence; never write an Amap address into source facts."""
    from src.services.collection_pipeline import active, auto_subject_reliable
    from src.services.directory_position_state import position_view
    from src.services.community_enrichment import valid_position
    from src.services.amap_directory import normalize_poi_category

    raw_address = community.get('source_address', community.get('address'))
    target = {**community, 'address': raw_address}
    def result(value='', origin=None, evidence=None, reason='地址待主体匹配'):
        return dict(value=value, origin=origin, evidence=evidence, valid=bool(value), reason=reason)
    def usable(value):
        return valid_address(value) and '..' not in value and '…' not in value
    if community.get('address_origin') == 'manual' and usable(raw_address):
        return result(raw_address.strip(), 'manual', reason='')
    verified = [r for r in records if not r.get('address_verification_pending') and usable(r.get('address'))]
    if verified:
        r = verified[0]
        return result(r['address'].strip(), r.get('address_evidence_kind') or 'source_detail',
                      dict(source_id=r.get('source_id'), url=r.get('address_evidence_url') or r.get('property_type_url')), '')
    if not active(target) or target.get(POLICY_KEY) != POLICY_RULE:
        return result(reason='实际地址资料缺失或待核实')
    view = position_view(target, records)
    point = view.get('selected') or {}
    district = (target.get('district') or '').removesuffix('区')
    if view.get('state') not in {'matched', 'manual'} or not usable(point.get('address')):
        return result()
    raw = dict(id=point.get('source_id'), name=point.get('name'), adname=(point.get('district') or '') + '区',
               address=point.get('address'), typecode=point.get('poi_typecode'),
               location=f'{point.get("longitude")},{point.get("latitude")}')
    if (not normalize_poi_category(raw, district=district)
            or not valid_position({**point, 'coordinate_system': 'gcj02'}, district)
            or not any(code.startswith('120') for code in str(point.get('poi_typecode') or '').split('|'))):
        return result(reason='高德主体区域、类型或坐标无效')
    if view['state'] == 'matched' and not auto_subject_reliable(target, point, records):
        return result(reason='高德主体身份待核对')
    areas = re.findall(r'(上城|拱墅|西湖|滨江|萧山|余杭|临平|钱塘|富阳|临安)区', point['address'])
    if any(area != district for area in areas):
        return result(reason='高德地址区域冲突')
    return result(point['address'].strip(), 'amap_subject', dict(
        poi_id=point['source_id'], name=point.get('name'), district=district,
        longitude=point['longitude'], latitude=point['latitude'], typecode=point.get('poi_typecode'),
        checked_at=view.get('confirmed_at') or view.get('checked_at'), identity=(target.get('amap_position') or {}).get('identity')), '')
