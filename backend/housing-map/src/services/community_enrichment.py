"""Bounded evidence/position repair. Association and human admission stay untouched."""
import json
import math
from pathlib import Path

from src.core.boundary import is_in_scope, is_in_xiaoshan_border
from src.services.community_address import valid_address
from src.services.community_registry import normalized, now


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8-sig')) if path.exists() else {}


def valid_position(record, district):
    lng, lat = record.get('longitude'), record.get('latitude')
    if record.get('coordinate_system') != 'gcj02' or not all(
        isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in (lng, lat)
    ):
        return False
    return is_in_scope(lng, lat) and (district != '萧山' or is_in_xiaoshan_border(lng, lat))


def historical_evidence(record, data_dir):
    if record['source'] != 'tmsf':
        return {}
    if record.get('source_kind') == 'project':
        return {}  # Newhouse projects share numeric IDs with ESF entries; no legacy lookup.
    data_dir = Path(data_dir)
    sid = str(record['source_id'])
    names = {normalized(n) for n in [record['name'], *record.get('aliases', [])] if n}
    values = {}
    legacy = read_json(data_dir / 'property_types.json').get(sid, {})
    if not record.get('property_type') and (not record.get('property_type_checked_at') or record.get('property_type_error')) and legacy.get('property_type'):
        values.update(property_type=legacy['property_type'], property_type_url=legacy.get('url'),
                      property_type_captured_at=legacy.get('captured_at'))
    # Price samples are only used for their verified source identity and address.
    path = data_dir / 'price_snapshots.jsonl'
    if not valid_address(record.get('address')) and path.exists():
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if not isinstance(row, dict) or str(row.get('community_id')) != sid or normalized(row.get('community_name')) not in names:
                continue
            address = row.get('raw_payload', {}).get('community', {}).get('address')
            if valid_address(address):
                values.update(address=address, address_evidence_url=row.get('source_url'), address_evidence_kind='historical_tmsf')
    district = (record.get('district') or '').removesuffix('区')
    coord = read_json(data_dir / 'binjiang_coordinates.json').get(sid, {})
    # The bundled coordinate file was produced by Amap geocoding (GCJ02).
    candidate = {**coord, 'coordinate_system': coord.get('coordinate_system', 'gcj02')}
    if not valid_position(record, district) and normalized(coord.get('name')) in names and district and district + '区' in (coord.get('formatted_address') or '') and valid_position(candidate, district):
        values.update(longitude=coord['longitude'], latitude=coord['latitude'], coordinate_system='gcj02', coordinate_error=None,
                      coordinate_evidence=dict(source='historical_amap', source_id=sid,
                                               formatted_address=coord['formatted_address']))
    return values


def qualified_address(address, district):
    if not valid_address(address):
        return ''
    if district + '区' in address:
        return address
    return f'杭州市{district}区{address}'


def source_position(community, records):
    """Project only current associated positions. Disagreement never picks an arbitrary point."""
    district = (community.get('district') or '').removesuffix('区')
    positioned = [r for r in records if r.get('longitude') is not None or r.get('latitude') is not None]
    if not positioned:
        return {}
    if any(not valid_position(r, district) for r in positioned):
        return {'coordinate_conflict': True}
    first = positioned[0]
    for other in positioned[1:]:
        dx = (first['longitude'] - other['longitude']) * math.cos(math.radians(first['latitude'])) * 111320
        if math.hypot(dx, (first['latitude'] - other['latitude']) * 111320) > 100:
            return {'coordinate_conflict': True}
    return {k: first[k] for k in ('longitude', 'latitude', 'coordinate_system')}


def _enrich_project_source(store, data_dir, record, tmsf_client):
    """Newhouse-only repair: direct project detail, no ESF page and no Amap position."""
    from src.services.tmsf_fetcher import TmsfClient
    from src.services.tmsf_property_type import fetch_project_facts_by_id
    names = [record['name'], *record.get('aliases', [])]
    district = (record.get('district') or '').removesuffix('区')
    if district not in {'滨江', '萧山'}:
        raise ValueError('来源区域不在目录范围')
    update = dict(property_type_checked_at=now())
    errors = []
    client = tmsf_client or TmsfClient()
    try:
        detail = fetch_project_facts_by_id(client, siteid=record.get('project_siteid'),
                                           propertyid=record.get('project_id'), names=names, district=district, previous=record)
        address_error = detail.pop('address_error', None)
        if address_error:
            detail.pop('address', None)  # Q1: a truncated address never lands on the row.
            errors.append(address_error)
        update.update(detail, property_type_captured_at=now(), property_type_error=None,
                      address_error=address_error, market_state_captured_at=now())
        if not address_error:
            update.update(address_origin='source_detail', address_checked_at=now(), address_verification_pending=False)
    except InterruptedError:
        raise
    except Exception as exc:
        code = getattr(exc, 'code', None)
        errors.append(f'新房详情获取失败（{code or type(exc).__name__}）：{exc}，保留已有证据')
        update['property_type_error'] = errors[-1]
    finally:
        if tmsf_client is None:
            client.close()
    # Network work is outside the writer; compare current identity before publication.
    with store.db() as db:
        current = db.execute('SELECT * FROM sources WHERE id=?', (record['id'],)).fetchone()
        if not current or store._source(current) != record:
            raise ValueError('来源已变化，请刷新后重试补全')
        payload = json.loads(current['payload'])
        db.execute('UPDATE sources SET payload=? WHERE id=?', (json.dumps({**payload, **update}, ensure_ascii=False), record['id']))
        store._event(db, current['cid'], 'source_enrichment', {'source_id': record['id'], 'evidence': update, 'errors': errors})
    from src.services.community_review import ReviewWorkspace
    ReviewWorkspace(store, data_dir).refresh()
    return dict(source_id=record['id'], errors=errors, updated_at=now())


def enrich_source(store, data_dir, rid, *, tmsf_client=None, amap_client=None, include_position=True):
    from src.services.tmsf_property_type import fetch_community_facts, fetch_project_facts, parse_project_index, find_project, project_identity, effective_market_state, PROJECT_INDEX_URL
    from src.services.tmsf_fetcher import TmsfClient
    from src.services.amap_directory import AmapClient, normalize_poi
    record = next((r for r in store.sources() if r['id'] == rid), None)
    if not record or record['status'] == 'ignored' or record['source'] != 'tmsf':
        raise ValueError('只能补全未忽略的透明售房网来源')
    if record.get('source_kind') == 'project':
        return _enrich_project_source(store, data_dir, record, tmsf_client)
    names = [record['name'], *record.get('aliases', [])]
    district = (record.get('district') or '').removesuffix('区')
    if district not in {'滨江', '萧山'}:
        raise ValueError('来源区域不在目录范围')
    update = historical_evidence(record, data_dir)
    update['property_type_checked_at'] = now()
    errors = []
    client = tmsf_client or TmsfClient()
    community_facts = None
    try:
        try:
            community_facts = fetch_community_facts(client, record['source_id'], names)
            if effective_market_state(record) == 'new_house':
                community_facts.pop('market_state', None)
            update.update(community_facts, property_type_captured_at=now(), property_type_error=None,
                          address_origin='source_detail', address_checked_at=now(), address_verification_pending=False,
                          listing_count_checked_at=now())
        except Exception:
            errors.append('小区详情更新失败，保留已有用途证据')
            update['property_type_error'] = errors[-1]
            update.update(listing_count_error=errors[-1], listing_count_checked_at=now())
        try:
            projects = parse_project_index(client.fetch_text(PROJECT_INDEX_URL, 15))
            identity = project_identity(find_project(projects, names, district))
            if identity['market_state'] == 'unknown' and community_facts:
                identity.pop('market_state')
            update.update(identity, market_state_captured_at=now())
            project = fetch_project_facts(client, names, district, projects=projects, previous=record)
            actual_address = (community_facts or record).get('address')
            if project.get('address') and valid_address(actual_address) and normalized(actual_address) != normalized(project['address']):
                raise ValueError('新房与小区地址冲突')
            address_error = project.get('address_error')
            if address_error:
                project.pop('address', None)
                errors.append(address_error)
            update.update({k: v for k, v in project.items() if k not in {'property_type', 'property_type_url'}})
            update['project_property_type_url'] = project['property_type_url']
            update.update(market_state_captured_at=now(), market_state_error=None,
                          project_property_type=project['property_type'])
            if not address_error:
                update.update(address_origin='source_detail', address_checked_at=now(), address_verification_pending=False)
            previous_type = (community_facts or {**record, **update}).get('property_type')
            if previous_type and previous_type != project['property_type']:
                update.update(property_type=previous_type, property_type_conflict=True)
            else:
                update.update(property_type=project['property_type'], property_type_url=project['property_type_url'], property_type_conflict=False,
                              property_type_captured_at=now(), property_type_error=None)
        except Exception:
            errors.append('新房项目更新失败或身份有歧义，保留已有证据')
            update['market_state_error'] = errors[-1]
    finally:
        if tmsf_client is None:
            client.close()
    effective = {**record, **update}
    if include_position and not valid_position(effective, district):
        client = amap_client
        try:
            client = client or AmapClient()
            pois, count = client.search_name(record['name'], district)
            matches = []
            for poi in pois:
                candidate = normalize_poi(poi, district=district)
                if candidate and normalized(candidate['name']) in {normalized(n) for n in names}:
                    address = effective.get('address')
                    if valid_address(address) and normalized(qualified_address(address, district)) != normalized(qualified_address(candidate['address'], district)):
                        continue
                    matches.append(candidate)
            unique = {r['source_id']: r for r in matches}
            if count > 25 or len(unique) != 1:
                raise ValueError('位置候选不唯一')
            point = next(iter(unique.values()))
            update.update({k: point[k] for k in ('longitude', 'latitude', 'coordinate_system')},
                          coordinate_evidence=dict(source='amap', source_id=point['source_id'],
                                                   source_url=point['source_url'], captured_at=now()),
                          coordinate_error=None)
            if not valid_address(effective.get('address')):
                update['address'] = point['address']
        except Exception:
            errors.append('位置补全失败或有歧义，需人工核对')
            update['coordinate_error'] = errors[-1]
        finally:
            if client is not None and amap_client is None:
                client.close()
    # Network work is outside the writer; compare current identity/decisions before publication.
    with store.db() as db:
        current = db.execute('SELECT * FROM sources WHERE id=?', (rid,)).fetchone()
        if not current or store._source(current) != record:
            raise ValueError('来源已变化，请刷新后重试补全')
        store._correct_source_address(db, current, update)
        payload = json.loads(current['payload'])
        db.execute('UPDATE sources SET payload=? WHERE id=?', (json.dumps({**payload, **update}, ensure_ascii=False), rid))
        store._event(db, current['cid'], 'source_enrichment', {'source_id': rid, 'evidence': update, 'errors': errors})
    from src.services.community_review import ReviewWorkspace
    ReviewWorkspace(store, data_dir).refresh()
    return dict(source_id=rid, errors=errors, updated_at=now())
