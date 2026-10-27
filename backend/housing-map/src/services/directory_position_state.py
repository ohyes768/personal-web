"""Position evidence is separate from admission, map visibility and source identities."""
import hashlib

from src.services.community_enrichment import valid_position
from src.services.community_registry import dump


def identity(target):
    target = {**target, 'address': target.get('source_address', target.get('address'))}
    return hashlib.sha256(dump({k: target.get(k) for k in
        ('community_id', 'community_name', 'aliases', 'district', 'address')}).encode()).hexdigest()


def position_view(target, records=()):
    district = (target.get('district') or '').removesuffix('区')
    has_coordinates = valid_position(target, district) or target.get('map_status') == 'displayed'
    saved = target.get('amap_position') or {}
    manual = next((item for item in [target, *records] if item.get('coordinate_origin') == 'manual'
                   or (item.get('coordinate_evidence') or {}).get('source') == 'manual'), None)
    if manual is not None:
        selected = saved.get('selected') or {}
        same_point = all(selected.get(k) == manual.get(k) for k in ('longitude', 'latitude'))
        if not (saved.get('identity') == identity(target) and saved.get('state') == 'manual' and same_point):
            return dict(state='manual', has_coordinates=has_coordinates, candidates=[], selected={
                k: manual.get(k) for k in ('longitude', 'latitude', 'geographic_address')})
    if saved and saved.get('identity') == identity(target):
        from src.services.collection_pipeline import active, auto_subject_reliable
        if active(target) and saved.get('state') == 'matched' and not auto_subject_reliable(target, saved.get('selected') or {}, records):
            point = saved.get('selected') or {}
            candidates = {p['source_id']: p for p in [point, *saved.get('candidates', [])] if p.get('source_id')}
            return dict(state='review', has_coordinates=has_coordinates, candidates=list(candidates.values()),
                        checked_at=saved.get('checked_at'), error='旧自动匹配不满足新主体规则，请核对地址与分期后确认')
        return {**{k: v for k, v in saved.items() if k != 'identity'}, 'has_coordinates': has_coordinates}
    if saved:
        return dict(state='pending', has_coordinates=has_coordinates, candidates=[],
                    query_history=dict(state='stale', checked_at=saved.get('checked_at'),
                                       message='地点资料已变化，待重新查询'),
                    error='小区身份或地址已变化，请重新匹配')
    # A geocoder/TMSF source id is not an Amap POI id. Ignore removed source rows.
    for item in [target, *records]:
        evidence = item.get('coordinate_evidence') or {}
        if evidence.get('source') == 'amap' and evidence.get('source_id') and valid_position(item, district):
            return dict(state='matched', has_coordinates=has_coordinates, candidates=[], selected=dict(
                source_id=evidence['source_id'], name=item.get('name') or target['community_name'],
                address=item.get('geographic_address') or evidence.get('formatted_address') or item.get('address'),
                longitude=item['longitude'], latitude=item['latitude'], source_url=evidence.get('source_url'),
                captured_at=evidence.get('captured_at')))
    view = dict(state='pending', has_coordinates=has_coordinates, candidates=[], error=None)
    # Legacy use searches are query history, never selected-subject evidence.
    from src.services.collection_pipeline import active
    from src.services.use_review_policy import use_identity, RULE_VERSION
    legacy = target.get('use_review') or {}
    if (active(target) and legacy.get('identity') == use_identity(target)
            and legacy.get('rule_version') == RULE_VERSION and legacy.get('checked_at')):
        state = legacy.get('state')
        messages = {'not_found': '历史未找到匹配地点，待重查', 'error': '历史查询失败，待重查',
                    'checked': '历史已查询，待匹配主体', 'uncertain': '历史查询待核实，待重查'}
        if state in messages:
            incomplete = state == 'uncertain' and any(s in (legacy.get('error') or '') for s in ('未完整', '未取完整'))
            view['query_history'] = dict(state='incomplete' if incomplete else state, checked_at=legacy['checked_at'],
                                        message='历史查询未完成，待重查' if incomplete else messages[state])
    return view
