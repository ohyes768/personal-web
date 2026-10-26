"""Position evidence is separate from admission, map visibility and source identities."""
import hashlib

from src.services.community_enrichment import valid_position
from src.services.community_registry import dump


def identity(target):
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
    return dict(state='pending', has_coordinates=has_coordinates, candidates=[],
                error='小区身份或地址已变化，请重新匹配' if saved else None)
